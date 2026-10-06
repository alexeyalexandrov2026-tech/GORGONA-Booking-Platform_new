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


class UnsupportedMediaTypeError(DomainError):
    code = "UNSUPPORTED_MEDIA_TYPE"


class FileScanningNotConfiguredError(DomainError):
    code = "FILE_SCANNING_NOT_CONFIGURED"


class FileIntegrityError(DomainError):
    code = "FILE_INTEGRITY_FAILED"


class InvalidFileNameError(DomainError):
    code = "INVALID_FILE_NAME"
