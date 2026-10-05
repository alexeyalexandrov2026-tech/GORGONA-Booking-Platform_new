"""File profile errors; no untrusted bytes or file names in messages."""

from gorgona_booking.errors import DomainError


class FileTooLargeError(DomainError):
    code = "FILE_TOO_LARGE"


class FileTypeMismatchError(DomainError):
    code = "FILE_TYPE_MISMATCH"


class FileUnreadableError(DomainError):
    code = "FILE_UNREADABLE"


class FileActiveContentError(DomainError):
    code = "FILE_ACTIVE_CONTENT"
