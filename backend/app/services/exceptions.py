class ServiceError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(ServiceError):
    """A requested application resource does not exist."""


class ConflictError(ServiceError):
    """A write conflicts with an existing application resource."""
