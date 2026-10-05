"""E2 bounded format profile: real structure, not a signature-only acceptance."""

import hashlib
import struct
import zlib

import pytest

from gorgona_booking.business.file_validation import (
    MAX_FILE_BYTES,
    FileActiveContentError,
    FileTooLargeError,
    FileTypeMismatchError,
    FileUnreadableError,
    validate_file,
)


def pdf(
    *extra: bytes,
    catalog: bytes = b"",
    pages: bytes = b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
    page: bytes = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 10 10] /Resources << >> >>",
) -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R " + catalog + b" >>",
        pages,
        page,
        *extra,
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode())
    data.extend(f"startxref\n{start}\n%%EOF\n".encode())
    return bytes(data)


def stream(data: bytes, attributes: bytes = b"") -> bytes:
    return (
        b"<< /Length "
        + str(len(data)).encode()
        + b" "
        + attributes
        + b" >>\nstream\n"
        + data
        + b"\nendstream"
    )


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png(*, text_bytes: int = 0) -> bytes:
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    text = chunk(b"tEXt", b"FAKE\0" + b"x" * text_bytes) if text_bytes else b""
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + text
        + chunk(b"IDAT", zlib.compress(b"\0\0\0\0"))
        + chunk(b"IEND", b"")
    )


def jpeg(sampling: tuple[int, ...] = (0x11,)) -> bytes:
    def segment(marker: int, value: bytes) -> bytes:
        return bytes([255, marker]) + struct.pack(">H", len(value) + 2) + value

    # Zero DC and EOB per block, then byte padding with one bits.
    counts = bytes([1] + [0] * 15)
    frame = b"\x08\x00\x01\x00\x01" + bytes([len(sampling)])
    scan = bytes([len(sampling)])
    for identifier, factor in enumerate(sampling, 1):
        frame += bytes([identifier, factor, 0])
        scan += bytes([identifier, 0])
    blocks = sum((factor >> 4) * (factor & 15) for factor in sampling)
    bit_count = 2 * (blocks if len(sampling) > 1 else 1)
    padding = (-bit_count) % 8
    entropy = ((1 << padding) - 1).to_bytes((bit_count + padding) // 8, "big")
    return (
        b"\xff\xd8"
        + segment(0xDB, b"\0" + bytes([1] * 64))
        + segment(0xC0, frame)
        + segment(0xC4, b"\0" + counts + b"\0" + b"\x10" + counts + b"\0")
        + segment(0xDA, scan + b"\x00\x3f\x00")
        + entropy
        + b"\xff\xd9"
    )


@pytest.mark.parametrize("sampling", [(0x33, 0x11, 0x11), (0x44, 0x44, 0x44)])
def test_jpeg_rejects_oversized_interleaved_mcu(sampling: tuple[int, ...]) -> None:
    with pytest.raises(FileUnreadableError):
        validate_file(jpeg(sampling), "image/jpeg", "FAKE.jpg")


@pytest.mark.parametrize("sampling", [(0x22, 0x11, 0x11), (0x42, 0x11, 0x11)])
def test_jpeg_accepts_interleaved_mcu_within_limit(sampling: tuple[int, ...]) -> None:
    assert validate_file(jpeg(sampling), "image/jpeg", "FAKE.jpg").media_type == "image/jpeg"


@pytest.mark.parametrize(
    ("data", "media"), [(pdf(), "application/pdf"), (png(), "image/png"), (jpeg(), "image/jpeg")]
)
def test_structured_files_have_exact_metadata(data: bytes, media: str) -> None:
    result = validate_file(data, media, "FAKE original.bad")
    assert result.media_type == media
    assert result.size_bytes == len(data)
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    assert result.scan_status == "not_scanned"
    assert result.validator_version == "gorgona-file-profile-v1"


@pytest.mark.parametrize(
    "name",
    [
        b"JavaScript",
        b"Java#53cript",
        b"JS",
        b"Launch",
        b"GoToR",
        b"GoToE",
        b"EmbeddedFiles",
        b"RichMedia",
        b"XFA",
        b"SubmitForm",
        b"ImportData",
    ],
)
def test_active_pdf_names_are_rejected_in_parsed_objects(name: bytes) -> None:
    with pytest.raises(FileActiveContentError):
        validate_file(pdf(b"<< /" + name + b" (FAKE) >>"), "application/pdf", "fake.pdf")


def test_open_action_plain_destination_is_allowed() -> None:
    validate_file(pdf(catalog=b"/OpenAction [3 0 R /Fit]"), "application/pdf", "fake.pdf")


def test_compressed_object_stream_cannot_hide_active_content() -> None:
    data = zlib.compress(b"4 0 << /Java#53cript (FAKE) >>")
    with pytest.raises(FileActiveContentError):
        validate_file(
            pdf(stream(data, b"/Type /ObjStm /N 1 /First 4 /Filter /FlateDecode")),
            "application/pdf",
            "fake.pdf",
        )


@pytest.mark.parametrize(
    "attribute",
    [
        b"/Filter /LZWDecode",
        b"/Filter 2 0 R",
        b"/Filter [/FlateDecode /FlateDecode]",
        b"/DecodeParms << /Predictor 12 >>",
        b"/F (external)",
        b"/FFilter /FlateDecode",
        b"/FDecodeParms null",
    ],
)
def test_unsupported_stream_forms_fail_closed(attribute: bytes) -> None:
    with pytest.raises(FileUnreadableError):
        validate_file(pdf(stream(zlib.compress(b"FAKE"), attribute)), "application/pdf", "fake.pdf")


@pytest.mark.parametrize(
    "body",
    [b"<< /A 1 /A 2 >>", b"<< /A#ZZ 1 >>", b"<< /A 999 0 R >>", b"[" * 40 + b"0" + b"]" * 40],
)
def test_ambiguous_or_invalid_pdf_syntax_is_refused(body: bytes) -> None:
    with pytest.raises(FileUnreadableError):
        validate_file(pdf(body), "application/pdf", "fake.pdf")


def test_encryption_and_bad_xref_and_trailing_payload_are_refused() -> None:
    for data in (
        pdf(catalog=b"/Encrypt << /V 1 >>"),
        pdf().replace(b"0000000009 00000 n", b"0000000008 00000 n"),
        pdf() + b"FAKE executable",
        pdf().replace(b"/Count 1", b"/Count 2"),
        b"%PDF-1.4\n%%EOF\n",
    ):
        with pytest.raises(FileUnreadableError):
            validate_file(data, "application/pdf", "fake.pdf")


def test_deflate_budget_is_aggregate_and_checks_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gorgona_booking.business.file_validation.MAX_DECODED_BYTES", 64)
    accepted = pdf(stream(zlib.compress(b"a" * 64), b"/Filter [/FlateDecode]"))
    validate_file(accepted, "application/pdf", "fake.pdf")
    refused = [
        pdf(stream(zlib.compress(b"a" * 65), b"/Filter /FlateDecode")),
        pdf(*[stream(zlib.compress(b"a" * 33), b"/Filter /FlateDecode")] * 2),
        pdf(stream(zlib.compress(b"a")[:-1], b"/Filter /FlateDecode")),
        pdf(stream(zlib.compress(b"a") + b"FAKE", b"/Filter /FlateDecode")),
    ]
    for data in refused:
        with pytest.raises(FileUnreadableError):
            validate_file(data, "application/pdf", "fake.pdf")


@pytest.mark.parametrize(
    "data",
    [
        png()[:-1],
        png() + b"FAKE",
        png().replace(b"IDAT", b"JUNK"),
        jpeg()[:-1],
        jpeg() + b"FAKE",
        b"\xff\xd8\xff\xd9",
    ],
)
def test_images_need_complete_supported_structure(data: bytes) -> None:
    media = "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
    with pytest.raises(FileUnreadableError):
        validate_file(data, media, "fake")


def test_exact_file_limit_and_one_extra_byte() -> None:
    overhead = len(png(text_bytes=1)) - 1
    data = png(text_bytes=MAX_FILE_BYTES - overhead)
    assert len(data) == MAX_FILE_BYTES
    validate_file(data, "image/png", "fake.png")
    with pytest.raises(FileTooLargeError):
        validate_file(data + b"x", "image/png", "fake.png")


@pytest.mark.parametrize(
    "name",
    [
        "../FAKE.exe",
        "C:\\bad\\CON.txt",
        "FAKE\u202e.exe",
        "x" * 200 + ".png",
        "COM¹.exe",
        "...",
        "bad\r\nname",
    ],
)
def test_names_are_safe_and_type_controls_extension(name: str) -> None:
    result = validate_file(png(), "image/png", name)
    assert result.file_name.endswith(".png")
    assert 1 <= len(result.file_name) <= 120
    assert not any(c in result.file_name for c in '/\\<>:"|?*\r\n\u202e')
    assert result.file_name.split(".")[0].upper() not in {"CON", "COM1"}


def test_type_mismatch_and_empty_body_are_refused() -> None:
    with pytest.raises(FileTypeMismatchError):
        validate_file(png(), "application/pdf", "fake.pdf")
    with pytest.raises(FileUnreadableError):
        validate_file(b"", "image/png", "fake.png")


def test_long_pdf_names_are_outside_the_bounded_profile() -> None:
    with pytest.raises(FileUnreadableError):
        validate_file(pdf(b"<< /" + b"A" * 128 + b" 1 >>"), "application/pdf", "fake.pdf")


@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        (b"gAMA", struct.pack(">I", 45455)),
        (b"pHYs", struct.pack(">IIB", 1, 1, 1)),
        (b"sRGB", b"\0"),
    ],
)
def test_png_color_and_physical_metadata_cannot_follow_idat(kind: bytes, payload: bytes) -> None:
    data = png()[:-12] + chunk(kind, payload) + chunk(b"IEND", b"")
    with pytest.raises(FileUnreadableError):
        validate_file(data, "image/png", "fake.png")


@pytest.mark.parametrize(
    "payload", [b" bad\0FAKE", b"bad \0FAKE", b"bad  word\0FAKE", b"bad\x01\0FAKE"]
)
def test_png_text_keyword_must_be_well_formed(payload: bytes) -> None:
    data = png()[:33] + chunk(b"tEXt", payload) + png()[33:]
    with pytest.raises(FileUnreadableError):
        validate_file(data, "image/png", "fake.png")


def test_jpeg_bad_huffman_symbols_are_refused() -> None:
    data = jpeg().replace(bytes([1] + [0] * 15) + b"\0", bytes([1] + [0] * 15) + b"\xff", 1)
    with pytest.raises(FileUnreadableError):
        validate_file(data, "image/jpeg", "fake.jpg")


@pytest.mark.parametrize("name", [b"EF", b"E#46", b"FileAttachment", b"File#41ttachment"])
def test_embedded_file_without_optional_type_is_refused(name: bytes) -> None:
    data = pdf(stream(b"FAKE file"), b"<< /" + name + b" << /F 4 0 R >> >>")
    with pytest.raises(FileActiveContentError):
        validate_file(data, "application/pdf", "fake.pdf")


def test_pdf_array_decimal_is_not_mistaken_for_reference_generation() -> None:
    data = pdf(catalog=b"/OpenAction [3 0 R /XYZ 0 612.0 792.0]")
    validate_file(data, "application/pdf", "fake.pdf")


@pytest.mark.parametrize(
    "geometry", [b"[0 0 0 10]", b"[0 0 10]", b"[true 0 10 10]", b"[0 0 10 10 10]"]
)
def test_invalid_page_geometry_is_refused(geometry: bytes) -> None:
    data = pdf(page=b"<< /Type /Page /Parent 2 0 R /MediaBox " + geometry + b" /Resources << >> >>")
    with pytest.raises(FileUnreadableError):
        validate_file(data, "application/pdf", "fake.pdf")


def test_catalog_pages_cannot_be_leaf_or_stream_object() -> None:
    leaf = b"<< /Type /Page /Count 1 /Kids [3 0 R] /MediaBox [0 0 10 10] /Resources << >> >>"
    page_stream = stream(
        b"FAKE", b"/Type /Page /Parent 2 0 R /MediaBox [0 0 10 10] /Resources << >>"
    )
    for data in (pdf(pages=leaf), pdf(page=page_stream)):
        with pytest.raises(FileUnreadableError):
            validate_file(data, "application/pdf", "fake.pdf")


def test_page_geometry_and_resources_can_be_inherited() -> None:
    data = pdf(
        pages=(
            b"<< /Type /Pages /Count 1 /Kids [3 0 R] "
            b"/MediaBox [0 0 612.0 792.0] /Resources << >> >>"
        ),
        page=b"<< /Type /Page /Parent 2 0 R >>",
    )
    validate_file(data, "application/pdf", "fake.pdf")


@pytest.mark.parametrize(
    "name", [b"OnInstantiate", b"On#49nstantiate", b"3D", b"3DD", b"3DA", b"3DRef"]
)
def test_three_d_lifecycle_cannot_execute_an_unnamed_script(name: bytes) -> None:
    data = pdf(
        stream(b"FAKE 3D bytes", b"/" + name + b" 5 0 R"),
        stream(zlib.compress(b"var fake = 1;"), b"/Filter /FlateDecode"),
    )
    with pytest.raises(FileActiveContentError):
        validate_file(data, "application/pdf", "fake.pdf")


@pytest.mark.parametrize(
    "body",
    [
        b"<< /UnknownFeature (FAKE) >>",
        b"<< /S /UnknownAction >>",
        b"<< /Subtype /UnknownPayload >>",
    ],
)
def test_unknown_pdf_features_are_outside_the_profile(body: bytes) -> None:
    with pytest.raises(FileUnreadableError):
        validate_file(pdf(body), "application/pdf", "fake.pdf")


def test_resource_names_are_not_confused_with_structural_keys() -> None:
    data = pdf(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        stream(b"BT /F1 12 Tf (FAKE text) Tj ET"),
        page=(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
    )
    validate_file(data, "application/pdf", "fake.pdf")
