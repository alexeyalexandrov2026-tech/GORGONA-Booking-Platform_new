"""Immutable metadata for a bounded file profile (E2 prerequisite).

This is structural validation, never a malware-free or rendering-safety verdict.
No parsing library, execution, network, filesystem, preview or scanner is used.
PNG: noninterlaced, 8-bit gray/RGB/gray-alpha/RGBA. JPEG: a single baseline frame
and scan, marker/table structure only. PDF: see pdf_validation's restricted profile.
"""

import hashlib
import struct
import unicodedata
import zlib
from dataclasses import dataclass
from typing import Literal

from gorgona_booking.business.file_errors import (
    FileActiveContentError as FileActiveContentError,
)
from gorgona_booking.business.file_errors import (
    FileTooLargeError as FileTooLargeError,
)
from gorgona_booking.business.file_errors import (
    FileTypeMismatchError as FileTypeMismatchError,
)
from gorgona_booking.business.file_errors import (
    FileUnreadableError as FileUnreadableError,
)
from gorgona_booking.business.pdf_validation import validate_pdf

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_DECODED_BYTES = 32 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_CHUNKS = 4096
VALIDATOR_VERSION = "gorgona-file-profile-v1"
type MediaType = Literal["application/pdf", "image/png", "image/jpeg"]
_EXTENSIONS = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}
_RESERVED = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CLOCK$",
        *[f"COM{i}" for i in range(1, 10)],
        *[f"LPT{i}" for i in range(1, 10)],
    }
)


@dataclass(frozen=True)
class ValidatedFile:
    media_type: MediaType
    size_bytes: int
    sha256: str
    file_name: str
    validator_version: str = VALIDATOR_VERSION
    scan_status: Literal["not_scanned"] = "not_scanned"


def _bad() -> FileUnreadableError:
    return FileUnreadableError("File does not meet the supported format profile")


class _Budget:
    def __init__(self) -> None:
        self.remaining = MAX_DECODED_BYTES

    def inflate(self, data: bytes) -> bytes:
        decoder = zlib.decompressobj()
        try:
            result = decoder.decompress(data, self.remaining + 1)
        except zlib.error as exc:
            raise _bad() from exc
        if (
            len(result) > self.remaining
            or not decoder.eof
            or decoder.unconsumed_tail
            or decoder.unused_data
        ):
            raise _bad()
        self.remaining -= len(result)
        return result


def safe_file_name(original: str, media_type: MediaType) -> str:
    if len(original) > 4096:
        raise _bad()
    name = unicodedata.normalize("NFC", original).replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(
        c
        for c in name
        if c.isprintable() and c not in '<>:"/\\|?*' and not unicodedata.category(c).startswith("C")
    )
    stem = name.rsplit(".", 1)[0].strip(" .") or "file"
    base = unicodedata.normalize("NFKC", stem.split(".", 1)[0]).upper()
    if base in _RESERVED:
        stem = "file-" + stem
    extension = _EXTENSIONS[media_type]
    return stem[: 120 - len(extension)].rstrip(" .") + extension


def _dimensions(width: int, height: int) -> None:
    if not 1 <= width <= 16384 or not 1 <= height <= 16384 or width * height > MAX_IMAGE_PIXELS:
        raise _bad()


def _png(data: bytes, budget: _Budget) -> None:
    position, chunks, channels, width, height = 8, 0, 0, 0, 0
    payloads: list[bytes] = []
    seen: set[bytes] = set()
    ended_idat = False
    while position < len(data):
        chunks += 1
        if chunks > MAX_CHUNKS or position + 12 > len(data):
            raise _bad()
        length = struct.unpack_from(">I", data, position)[0]
        kind = data[position + 4 : position + 8]
        end = position + 12 + length
        if end > len(data):
            raise _bad()
        payload = data[position + 8 : end - 4]
        if struct.unpack_from(">I", data, end - 4)[0] != zlib.crc32(payload, zlib.crc32(kind)):
            raise _bad()
        if chunks == 1 and kind != b"IHDR":
            raise _bad()
        if kind == b"IHDR":
            if kind in seen or length != 13:
                raise _bad()
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            _dimensions(width, height)
            if (depth, compression, filtering, interlace) != (8, 0, 0, 0) or color not in (
                0,
                2,
                4,
                6,
            ):
                raise _bad()
            channels = {0: 1, 2: 3, 4: 2, 6: 4}[color]
        elif kind == b"IDAT":
            if ended_idat:
                raise _bad()
            payloads.append(payload)
        elif kind == b"IEND":
            if length or end != len(data) or not payloads:
                raise _bad()
            pixels = budget.inflate(b"".join(payloads))
            stride = width * channels + 1
            if len(pixels) != height * stride or any(
                pixels[row * stride] > 4 for row in range(height)
            ):
                raise _bad()
            return
        elif kind == b"tEXt":
            keyword = payload.split(b"\0", 1)
            if (
                len(keyword) != 2
                or not 1 <= len(keyword[0]) <= 79
                or b"\0" in keyword[1]
                or keyword[0].startswith(b" ")
                or keyword[0].endswith(b" ")
                or b"  " in keyword[0]
                or any(c < 32 or 126 < c < 161 for c in keyword[0])
            ):
                raise _bad()
        elif kind in (b"gAMA", b"cHRM", b"pHYs", b"sRGB"):
            if (
                payloads
                or kind in seen
                or length != {b"gAMA": 4, b"cHRM": 32, b"pHYs": 9, b"sRGB": 1}[kind]
            ):
                raise _bad()
            if kind == b"sRGB" and payload[0] > 3:
                raise _bad()
            if kind == b"gAMA" and not struct.unpack(">I", payload)[0]:
                raise _bad()
            if kind == b"pHYs" and payload[8] > 1:
                raise _bad()
            if kind == b"cHRM":
                values = struct.unpack(">8I", payload)
                if any(values[i] + values[i + 1] > 100_000 for i in range(0, 8, 2)):
                    raise _bad()
        else:
            # No compressed text, profiles, animation or unknown ancillary data.
            raise _bad()
        if payloads and kind != b"IDAT":
            ended_idat = True
        seen.add(kind)
        position = end
    raise _bad()


def _jpeg(data: bytes) -> None:
    position, segments = 2, 0
    components: dict[int, int] = {}
    interleaved_blocks = 0
    quantization: set[int] = set()
    huffman: set[int] = set()
    while position < len(data):
        segments += 1
        if segments > MAX_CHUNKS or position + 4 > len(data) or data[position] != 255:
            raise _bad()
        marker = data[position + 1]
        length = struct.unpack_from(">H", data, position + 2)[0]
        end = position + 2 + length
        if length < 2 or end > len(data):
            raise _bad()
        body = data[position + 4 : end]
        if marker == 0xDB:
            if not body or len(body) % 65:
                raise _bad()
            for offset in range(0, len(body), 65):
                table = body[offset]
                if table > 3 or any(value == 0 for value in body[offset + 1 : offset + 65]):
                    raise _bad()
                quantization.add(table)
        elif marker == 0xC4:
            if not body:
                raise _bad()
            offset = 0
            while offset < len(body):
                if offset + 17 > len(body) or body[offset] not in (0, 1, 2, 3, 16, 17, 18, 19):
                    raise _bad()
                counts = body[offset + 1 : offset + 17]
                available = 1
                for count in counts:
                    available = available * 2 - count
                    if available <= 0:
                        raise _bad()
                count = sum(counts)
                if not 1 <= count <= 256 or offset + 17 + count > len(body):
                    raise _bad()
                symbols = body[offset + 17 : offset + 17 + count]
                if body[offset] < 16:
                    if any(s > 11 for s in symbols):
                        raise _bad()
                elif any(s not in (0, 240) and not 1 <= s & 15 <= 10 for s in symbols):
                    raise _bad()
                huffman.add(body[offset])
                offset += 17 + count
        elif marker == 0xC0:
            if (
                components
                or len(body) < 6
                or body[0] != 8
                or body[5] not in (1, 3)
                or len(body) != 6 + 3 * body[5]
            ):
                raise _bad()
            height, width = struct.unpack_from(">HH", body, 1)
            _dimensions(width, height)
            for offset in range(6, len(body), 3):
                identifier, sampling, table = body[offset : offset + 3]
                if (
                    identifier in components
                    or not 1 <= sampling >> 4 <= 4
                    or not 1 <= sampling & 15 <= 4
                    or table > 3
                ):
                    raise _bad()
                components[identifier] = table
                interleaved_blocks += (sampling >> 4) * (sampling & 15)
        elif marker == 0xDA:
            if (
                not components
                or len(body) != 1 + 2 * len(components) + 3
                or body[0] != len(components)
                or (len(components) > 1 and interleaved_blocks > 10)
                or body[-3:] != b"\0\x3f\0"
            ):
                raise _bad()
            scan: set[int] = set()
            for offset in range(1, len(body) - 3, 2):
                identifier, tables = body[offset : offset + 2]
                if (
                    identifier in scan
                    or identifier not in components
                    or components[identifier] not in quantization
                    or tables >> 4 not in huffman
                    or 16 + (tables & 15) not in huffman
                ):
                    raise _bad()
                scan.add(identifier)
            if scan != set(components) or end >= len(data) - 2:
                raise _bad()
            position = end
            while position < len(data):
                if data[position] != 255:
                    position += 1
                elif data[position : position + 2] == b"\xff\0":
                    position += 2
                elif data[position : position + 2] == b"\xff\xd9" and position + 2 == len(data):
                    return
                else:
                    raise _bad()
            raise _bad()
        elif not (0xE0 <= marker <= 0xEF or marker == 0xFE):
            # Progressive, arithmetic, lossless, restart and multi-scan profiles
            # require a reviewed decoder and are not silently treated as valid.
            raise _bad()
        position = end
    raise _bad()


def validate_file(content: bytes, declared_type: str, original_name: str) -> ValidatedFile:
    if len(content) > MAX_FILE_BYTES:
        raise FileTooLargeError("Files must not exceed 10 MiB")
    if not content:
        raise _bad()
    media: MediaType
    if content.startswith(b"%PDF-"):
        media = "application/pdf"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        media = "image/png"
    elif content.startswith(b"\xff\xd8"):
        media = "image/jpeg"
    else:
        raise FileTypeMismatchError("Unsupported file type")
    if declared_type != media:
        raise FileTypeMismatchError("Declared file type does not match the content")
    budget = _Budget()
    if media == "application/pdf":
        validate_pdf(content, budget.inflate)
    elif media == "image/png":
        _png(content, budget)
    else:
        _jpeg(content)
    return ValidatedFile(
        media,
        len(content),
        hashlib.sha256(content).hexdigest(),
        safe_file_name(original_name, media),
    )
