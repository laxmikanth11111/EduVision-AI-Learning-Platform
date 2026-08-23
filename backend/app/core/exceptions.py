from __future__ import annotations

from typing import Any

from app.core.error_codes import ErrorCode


class EduVisionError(Exception):
    def __init__(
        self,
        message: str = "An unexpected error occurred",
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }


class NotFoundError(EduVisionError):
    def __init__(
        self,
        message: str = "Resource not found",
        code: ErrorCode = ErrorCode.NOT_FOUND,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=404, details=details)


class ConflictError(EduVisionError):
    def __init__(
        self,
        message: str = "Resource already exists",
        code: ErrorCode = ErrorCode.CONFLICT,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=409, details=details)


class ValidationError(EduVisionError):
    def __init__(
        self,
        message: str = "Validation failed",
        code: ErrorCode = ErrorCode.VALIDATION_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=422, details=details)


class UnauthorizedError(EduVisionError):
    def __init__(
        self,
        message: str = "Unauthorized",
        code: ErrorCode = ErrorCode.UNAUTHORIZED,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=401, details=details)


class ForbiddenError(EduVisionError):
    def __init__(
        self,
        message: str = "Forbidden",
        code: ErrorCode = ErrorCode.FORBIDDEN,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=403, details=details)


PermissionDeniedError = ForbiddenError


class ServiceUnavailableError(EduVisionError):
    def __init__(
        self,
        message: str = "Service temporarily unavailable",
        code: ErrorCode = ErrorCode.SERVICE_UNAVAILABLE,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=503, details=details)


class DatabaseError(EduVisionError):
    def __init__(
        self,
        message: str = "Database operation failed",
        code: ErrorCode = ErrorCode.DATABASE_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=500, details=details)


class StorageError(EduVisionError):
    def __init__(
        self,
        message: str = "Storage operation failed",
        code: ErrorCode = ErrorCode.STORAGE_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=500, details=details)


class ConfigurationError(EduVisionError):
    def __init__(
        self,
        message: str = "Configuration error",
        code: ErrorCode = ErrorCode.CONFIGURATION_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=500, details=details)


class RateLimitError(EduVisionError):
    def __init__(
        self,
        message: str = "Too many requests",
        code: ErrorCode = ErrorCode.RATE_LIMITED,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=429, details=details)


class IntegrityError(EduVisionError):
    def __init__(
        self,
        message: str = "Data integrity violation",
        code: ErrorCode = ErrorCode.INTEGRITY_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=409, details=details)


class ExtractionError(EduVisionError):
    def __init__(
        self,
        message: str = "Content extraction failed",
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, code=code, status_code=500, details=details)
