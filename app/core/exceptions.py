class AtlasError(Exception):
    pass


class NotFoundError(AtlasError):
    def __init__(self, message: str = "Resource not found"):
        self.message = message
        super().__init__(message)


class ForbiddenError(AtlasError):
    def __init__(self, message: str = "Permission denied"):
        self.message = message
        super().__init__(message)


class AppValidationError(AtlasError):
    def __init__(self, message: str, field: str | None = None):
        self.message = message
        self.field = field
        super().__init__(message)


class AuthenticationError(AtlasError):
    def __init__(self, message: str = "Authentication failed"):
        self.message = message
        super().__init__(message)


class ConflictError(AtlasError):
    def __init__(self, message: str = "Resource already exists"):
        self.message = message
        super().__init__(message)


class RateLimitError(AtlasError):
    def __init__(self, message: str = "Rate limit exceeded"):
        self.message = message
        super().__init__(message)


class FileTooLargeError(AtlasError):
    def __init__(self, message: str = "File exceeds the maximum allowed size"):
        self.message = message
        super().__init__(message)


class ServiceUnavailableError(AtlasError):
    def __init__(self, message: str = "Service temporarily unavailable"):
        self.message = message
        super().__init__(message)
