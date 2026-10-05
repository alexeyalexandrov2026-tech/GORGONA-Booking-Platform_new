"""Bounded conservative PDF profile, not a general-purpose PDF reader.

Single classic xref, generation-zero objects, direct stream lengths, raw/Flate
streams. Unsupported compressed object/xref streams, filters and incremental
updates fail closed. Parsed names/references, xref offsets and page tree are
checked; compressed bytes have one aggregate budget supplied by the caller.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from gorgona_booking.business.file_errors import FileActiveContentError, FileUnreadableError

MAX_OBJECTS = 4096
MAX_DEPTH = 32
MAX_TOKENS = 100_000
_WS = b"\x00\t\n\f\r "
_DELIMITERS = _WS + b"()<>[]{}/%"
_NUMBER = re.compile(rb"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")
_COMMENT_END = re.compile(rb"[\r\n]")
_ACTIVE = frozenset(
    {
        "JavaScript",
        "JS",
        "Launch",
        "EmbeddedFile",
        "EmbeddedFiles",
        "EF",
        "FileAttachment",
        "Filespec",
        "AF",
        "OnInstantiate",
        "3D",
        "3DD",
        "3DA",
        "3DRef",
        "RichMedia",
        "XFA",
        "SubmitForm",
        "ImportData",
        "GoToR",
        "GoToE",
        "URI",
        "Rendition",
        "Movie",
        "Sound",
        "ResetForm",
    }
)


@dataclass(frozen=True)
class Name:
    value: str


@dataclass(frozen=True)
class Reference:
    number: int


type Value = Name | Reference | bytes | int | float | bool | list[Value] | dict[str, Value] | None

# The profile supports a finite dictionary vocabulary. A deny-list alone cannot
# establish that an unknown extension, action or payload is passive. Names inside
# resource maps remain business-independent PDF identifiers (e.g. Font/F1).
_RESOURCE_MAPS = frozenset(
    {"Font", "XObject", "ExtGState", "ColorSpace", "Pattern", "Shading", "Properties"}
)
_RESOURCE_KEYS = _RESOURCE_MAPS | {"ProcSet"}
_KEYS = frozenset(
    {
        "Type",
        "Subtype",
        "Length",
        "Filter",
        "Size",
        "Root",
        "Info",
        "ID",
        "Pages",
        "Parent",
        "Kids",
        "Count",
        "MediaBox",
        "CropBox",
        "Rotate",
        "Resources",
        "Contents",
        "Font",
        "XObject",
        "ExtGState",
        "ColorSpace",
        "ProcSet",
        "BaseFont",
        "Encoding",
        "ToUnicode",
        "FirstChar",
        "LastChar",
        "Widths",
        "FontDescriptor",
        "FontName",
        "Flags",
        "FontBBox",
        "ItalicAngle",
        "Ascent",
        "Descent",
        "CapHeight",
        "StemV",
        "MissingWidth",
        "FontFile",
        "FontFile2",
        "FontFile3",
        "Length1",
        "Length2",
        "Length3",
        "DescendantFonts",
        "CIDSystemInfo",
        "Registry",
        "Ordering",
        "Supplement",
        "CIDToGIDMap",
        "DW",
        "W",
        "Differences",
        "Width",
        "Height",
        "BitsPerComponent",
        "ImageMask",
        "Decode",
        "Interpolate",
        "BBox",
        "Matrix",
        "FormType",
        "Name",
        "S",
        "D",
        "A",
        "OpenAction",
        "Annots",
        "Rect",
        "Border",
        "C",
        "H",
        "P",
        "F",
        "Dest",
        "Title",
        "Author",
        "Creator",
        "Producer",
        "Subject",
        "Keywords",
        "CreationDate",
        "ModDate",
        "Trapped",
    }
)
_TYPES = frozenset(
    {
        "Catalog",
        "Pages",
        "Page",
        "Font",
        "FontDescriptor",
        "XObject",
        "ExtGState",
        "Encoding",
        "Action",
        "Annot",
    }
)
_SUBTYPES = frozenset(
    {
        "Type1",
        "TrueType",
        "Type0",
        "CIDFontType0",
        "CIDFontType2",
        "MMType1",
        "Form",
        "Image",
        "Link",
        "Text",
    }
)


def _bad() -> FileUnreadableError:
    return FileUnreadableError("File does not meet the supported PDF profile")


def _name(raw: bytes) -> str:
    if len(raw) > 381:
        raise _bad()
    decoded = bytearray()
    index = 0
    while index < len(raw):
        if raw[index] == 35:
            if index + 2 >= len(raw) or not re.fullmatch(
                rb"[0-9a-fA-F]{2}", raw[index + 1 : index + 3]
            ):
                raise _bad()
            decoded.append(int(raw[index + 1 : index + 3], 16))
            index += 3
        else:
            decoded.append(raw[index])
            index += 1
    if not decoded or len(decoded) > 127 or 0 in decoded:
        raise _bad()
    text = decoded.decode("latin-1")
    if text in _ACTIVE:
        raise FileActiveContentError("Active PDF content is not allowed")
    if text == "Encrypt":
        raise _bad()
    return text


class _Parser:
    def __init__(self, data: bytes, position: int = 0) -> None:
        self.data = data
        self.position = position
        self.tokens = 0

    def skip(self) -> None:
        while self.position < len(self.data):
            char = self.data[self.position]
            if char in _WS:
                self.position += 1
            elif char == 37:
                end = _COMMENT_END.search(self.data, self.position)
                self.position = len(self.data) if end is None else end.end()
            else:
                break

    def word(self) -> bytes:
        self.skip()
        start = self.position
        while self.position < len(self.data) and self.data[self.position] not in _DELIMITERS:
            self.position += 1
            if self.position - start > 381:
                raise _bad()
        word = self.data[start : self.position]
        self.tokens += 1
        if not word or self.tokens > MAX_TOKENS:
            raise _bad()
        return word

    def expect(self, value: bytes) -> None:
        if self.word() != value:
            raise _bad()

    def integer(self) -> int:
        token = self.word()
        if len(token) > 10 or not token.isdigit():
            raise _bad()
        return int(token)

    def value(self, depth: int = 0) -> Value:
        if depth > MAX_DEPTH:
            raise _bad()
        self.skip()
        self.tokens += 1
        if self.tokens > MAX_TOKENS or self.position >= len(self.data):
            raise _bad()
        if self.data.startswith(b"<<", self.position):
            self.position += 2
            result: dict[str, Value] = {}
            while True:
                self.skip()
                if self.data.startswith(b">>", self.position):
                    self.position += 2
                    return result
                key = self.value(depth + 1)
                if not isinstance(key, Name) or key.value in result:
                    raise _bad()
                result[key.value] = self.value(depth + 1)
        char = self.data[self.position]
        if char == 91:
            self.position += 1
            items: list[Value] = []
            while True:
                self.skip()
                if self.position >= len(self.data):
                    raise _bad()
                if self.data[self.position] == 93:
                    self.position += 1
                    return items
                items.append(self.value(depth + 1))
        if char == 47:
            self.position += 1
            return Name(_name(self.word()))
        if char == 40:
            self.position += 1
            start, nested = self.position, 1
            while self.position < len(self.data):
                current = self.data[self.position]
                self.position += 1
                if current == 92:
                    self.position += 1
                elif current == 40:
                    nested += 1
                    if nested > MAX_DEPTH:
                        raise _bad()
                elif current == 41:
                    nested -= 1
                    if not nested:
                        return self.data[start : self.position - 1]
            raise _bad()
        if char == 60:
            end = self.data.find(b">", self.position + 1)
            if end < 0:
                raise _bad()
            text = bytes(c for c in self.data[self.position + 1 : end] if c not in _WS)
            if not re.fullmatch(rb"[0-9a-fA-F]*", text):
                raise _bad()
            self.position = end + 1
            return bytes.fromhex((text + (b"0" if len(text) % 2 else b"")).decode("ascii"))
        word = self.word()
        if word in (b"true", b"false", b"null"):
            return {b"true": True, b"false": False, b"null": None}[word]
        if len(word) > 32 or not _NUMBER.fullmatch(word):
            raise _bad()
        if b"." in word:
            return float(word)
        number = int(word)
        saved = self.position
        self.skip()
        if self.position < len(self.data) and self.data[self.position] in b"0123456789":
            token = self.word()
            self.skip()
            if token.isdigit() and len(token) <= 5 and self.data.startswith(b"R", self.position):
                self.expect(b"R")
                if number <= 0 or int(token) != 0:
                    raise _bad()
                return Reference(number)
        self.position = saved
        return number


def _stream(parser: _Parser, value: Value, inflate: Callable[[bytes], bytes]) -> None:
    parser.skip()
    if not parser.data.startswith(b"stream", parser.position):
        return
    parser.expect(b"stream")
    if not isinstance(value, dict) or type(value.get("Length")) is not int:
        raise _bad()
    if value.get("Type") in (Name("Catalog"), Name("Pages"), Name("Page")):
        raise _bad()
    length = value["Length"]
    if not isinstance(length, int) or length < 0:
        raise _bad()
    if parser.data.startswith(b"\r\n", parser.position):
        parser.position += 2
    elif parser.data.startswith(b"\n", parser.position):
        parser.position += 1
    else:
        raise _bad()
    end = parser.position + length
    if end > len(parser.data) or any(
        k in value for k in ("F", "FFilter", "FDecodeParms", "DecodeParms")
    ):
        raise _bad()
    data = parser.data[parser.position : end]
    parser.position = end
    parser.expect(b"endstream")
    filter_value = value.get("Filter")
    if filter_value == Name("FlateDecode") or filter_value == [Name("FlateDecode")]:
        data = inflate(data)
    elif filter_value is not None:
        raise _bad()
    # Decode names in every decoded stream too. This deliberately conservative
    # profile can refuse harmless name-like bytes; it never skips opaque filters.
    for match in re.finditer(rb"/([^\x00\t\n\f\r ()<>\[\]{}/%]+)", data):
        if match.end(1) - match.start(1) > 381:
            raise _bad()
        _name(match[1])
    if value.get("Type") in (Name("ObjStm"), Name("XRef")):
        raise _bad()


def _references(objects: dict[int, Value], trailer: dict[str, Value]) -> None:
    pending: list[Value] = [*objects.values(), trailer]
    while pending:
        value = pending.pop()
        if isinstance(value, Reference):
            if value.number not in objects:
                raise _bad()
        elif isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)


def _features(objects: dict[int, Value], trailer: dict[str, Value]) -> None:
    pending: list[tuple[Value, bool]] = [(v, False) for v in [*objects.values(), trailer]]
    while pending:
        value, resource_map = pending.pop()
        if isinstance(value, dict):
            if not resource_map and not set(value) <= _KEYS:
                raise _bad()
            if not resource_map:
                for key, allowed in (("Type", _TYPES), ("Subtype", _SUBTYPES), ("S", {"GoTo"})):
                    if key in value:
                        field = value[key]
                        if not isinstance(field, Name) or field.value not in allowed:
                            raise _bad()
            pending.extend(
                (child, not resource_map and key in _RESOURCE_MAPS) for key, child in value.items()
            )
        elif isinstance(value, list):
            pending.extend((child, False) for child in value)


def _pages(objects: dict[int, Value], root: Value) -> None:
    if not isinstance(root, Reference):
        raise _bad()
    catalog = objects.get(root.number)
    if not isinstance(catalog, dict) or catalog.get("Type") != Name("Catalog"):
        raise _bad()
    visited: set[int] = set()

    def visit(
        ref: Value,
        parent: Reference | None,
        media_box: Value = None,
        resources: Value = None,
        depth: int = 0,
    ) -> int:
        if not isinstance(ref, Reference) or ref.number in visited or depth > MAX_DEPTH:
            raise _bad()
        visited.add(ref.number)
        page = objects.get(ref.number)
        if not isinstance(page, dict) or (parent is not None and page.get("Parent") != parent):
            raise _bad()
        if parent is None and ("Parent" in page or page.get("Type") != Name("Pages")):
            raise _bad()
        media_box = page.get("MediaBox", media_box)
        resources = page.get("Resources", resources)
        if page.get("Type") == Name("Page"):
            if isinstance(media_box, Reference):
                media_box = objects.get(media_box.number)
            if not isinstance(media_box, list) or len(media_box) != 4:
                raise _bad()
            coordinates: list[float] = []
            for coordinate in media_box:
                if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
                    raise _bad()
                coordinates.append(float(coordinate))
            if coordinates[2] <= coordinates[0] or coordinates[3] <= coordinates[1]:
                raise _bad()
            if isinstance(resources, Reference):
                resources = objects.get(resources.number)
            if not isinstance(resources, dict):
                raise _bad()
            if not set(resources) <= _RESOURCE_KEYS:
                raise _bad()
            return 1
        if page.get("Type") != Name("Pages") or not isinstance(page.get("Kids"), list):
            raise _bad()
        kids = page["Kids"]
        if not isinstance(kids, list):
            raise _bad()
        count = sum(visit(kid, ref, media_box, resources, depth + 1) for kid in kids)
        if type(page.get("Count")) is not int or page["Count"] != count:
            raise _bad()
        return count

    if visit(catalog.get("Pages"), None) < 1:
        raise _bad()


def validate_pdf(data: bytes, inflate: Callable[[bytes], bytes]) -> None:
    header = re.match(rb"%PDF-1\.[0-7](?:\r\n|\n)", data)
    if header is None:
        raise _bad()
    parser = _Parser(data, header.end())
    objects: dict[int, Value] = {}
    offsets: dict[int, int] = {}
    while True:
        parser.skip()
        position = parser.position
        if data.startswith(b"xref", position):
            break
        number = parser.integer()
        if number < 1 or number > MAX_OBJECTS or number in objects or parser.integer() != 0:
            raise _bad()
        parser.expect(b"obj")
        value = parser.value()
        _stream(parser, value, inflate)
        parser.expect(b"endobj")
        objects[number], offsets[number] = value, position
    xref_position = parser.position
    parser.expect(b"xref")
    entries: dict[int, int] = {}
    saw_zero = False
    while True:
        parser.skip()
        if data.startswith(b"trailer", parser.position):
            break
        first, count = parser.integer(), parser.integer()
        if count < 1 or first + count > MAX_OBJECTS + 1:
            raise _bad()
        for number in range(first, first + count):
            offset, generation, kind = parser.integer(), parser.integer(), parser.word()
            if number == 0:
                if saw_zero or (offset, generation, kind) != (0, 65535, b"f"):
                    raise _bad()
                saw_zero = True
            else:
                if number in entries or generation != 0 or kind != b"n":
                    raise _bad()
                entries[number] = offset
    parser.expect(b"trailer")
    trailer = parser.value()
    if not isinstance(trailer, dict) or any(k in trailer for k in ("Prev", "XRefStm")):
        raise _bad()
    if not objects or not saw_zero or entries != offsets or trailer.get("Size") != max(objects) + 1:
        raise _bad()
    parser.expect(b"startxref")
    if parser.integer() != xref_position:
        raise _bad()
    if not re.fullmatch(rb"[\x00\t\n\f\r ]*%%EOF[\x00\t\n\f\r ]*", data[parser.position :]):
        raise _bad()
    _references(objects, trailer)
    _features(objects, trailer)
    _pages(objects, trailer.get("Root"))
