"""Versioned document contracts (ADR-0020 E2, ADR-0021 file profile).

A document holds what the business entered: a title, a category, optional validity
dates and at most one validated file per version. Files are never previewed, scanned
or interpreted here; `not_scanned` states that no malware verdict exists.
"""

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, field_validator, model_validator

from gorgona_booking.business.contracts import Strict, Versioned

DocumentCategory = Literal["agreement", "certificate", "invoice", "report", "other"]
MediaType = Literal["application/pdf", "image/png", "image/jpeg"]
MEDIA_TYPES: frozenset[str] = frozenset({"application/pdf", "image/png", "image/jpeg"})
_MAX_REVISION = 2_147_483_646


class DocumentInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION)
    title: str = Field(min_length=1, max_length=200)
    category: DocumentCategory
    valid_from: date | None = None
    valid_until: date | None = None
    archived: StrictBool = False
    file_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        title = value.strip()
        if not title or any(ord(char) < 32 or ord(char) == 127 for char in title):
            raise ValueError("Provide a nonblank title without control characters")
        return title

    @model_validator(mode="after")
    def ordered_validity(self) -> Self:
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until < self.valid_from
        ):
            raise ValueError("The end of validity cannot precede its start")
        return self


class FileMetadata(Strict):
    file_id: UUID
    media_type: MediaType
    size_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_name: str
    validator_version: str
    # No scanner exists; this never means "safe".
    scan_status: Literal["not_scanned"] = "not_scanned"
    uploaded_at: AwareDatetime


class DocumentFileView(FileMetadata):
    schema_version: Literal[1] = 1
    business_id: UUID


class DocumentFileReceipt(Strict):
    """What an upload stores under its key: a reference, never bytes or a file name."""

    file_id: UUID


class DocumentView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    document_id: UUID
    revision: int = Field(ge=1)
    title: str
    category: DocumentCategory
    valid_from: date | None
    valid_until: date | None
    archived: bool
    file: FileMetadata | None
    created_at: AwareDatetime


class DocumentReceipt(Strict):
    document_id: UUID
    revision: int


class DocumentSummary(Strict):
    document_id: UUID
    revision: int = Field(ge=1)
    title: str
    category: DocumentCategory
    valid_from: date | None
    valid_until: date | None
    archived: bool
    media_type: MediaType | None
    updated_at: AwareDatetime


class DocumentList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    # Uploads are refused where no malware scanner is configured (staging, production).
    file_uploads: Literal["enabled", "scanner_not_configured"]
    items: tuple[DocumentSummary, ...]
    next_cursor: UUID | None


class DocumentRevision(Strict):
    revision: int = Field(ge=1)
    title: str
    archived: bool
    file_id: UUID | None
    created_at: AwareDatetime


class DocumentHistory(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    document_id: UUID
    items: tuple[DocumentRevision, ...]
    next_cursor: int | None


class LinkCounterpartyInput(Versioned):
    action: Literal["link"]
    counterparty_id: UUID


class UnlinkCounterpartyInput(Versioned):
    action: Literal["unlink"]
    counterparty_id: UUID
    expected_sequence: StrictInt = Field(ge=1, le=_MAX_REVISION)


DocumentLinkInput = Annotated[
    LinkCounterpartyInput | UnlinkCounterpartyInput, Field(discriminator="action")
]


class DocumentLinkView(Strict):
    link_id: UUID
    document_id: UUID
    counterparty_id: UUID
    sequence: int = Field(ge=1)
    action: Literal["linked", "unlinked"]
    decided_at: AwareDatetime


class DocumentLinkResult(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    document_id: UUID
    link: DocumentLinkView


class DocumentLinkReceipt(Strict):
    link_id: UUID


class LinkedCounterparty(Strict):
    counterparty_id: UUID
    display_name: str
    state: Literal["active", "archived", "merged"]
    sequence: int = Field(ge=1)
    decided_at: AwareDatetime


class DocumentLinks(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    document_id: UUID
    # Counterparties currently linked, and the full event history (newest first).
    current: tuple[LinkedCounterparty, ...]
    history: tuple[DocumentLinkView, ...]


class LinkedDocument(Strict):
    document: DocumentSummary
    # The linked record: this counterparty or a duplicate merged into it.
    counterparty_id: UUID
    sequence: int = Field(ge=1)
    decided_at: AwareDatetime


class CounterpartyDocuments(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    counterparty_id: UUID
    items: tuple[LinkedDocument, ...]
    next_cursor: UUID | None
