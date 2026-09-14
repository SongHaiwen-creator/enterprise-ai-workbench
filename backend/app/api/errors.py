from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.exceptions import ConflictError, NotFoundError


async def not_found_error_handler(
    request: Request,
    exc: NotFoundError,
) -> JSONResponse:
    del request
    return JSONResponse(status_code=404, content={"detail": exc.detail})


async def conflict_error_handler(
    request: Request,
    exc: ConflictError,
) -> JSONResponse:
    del request
    return JSONResponse(status_code=409, content={"detail": exc.detail})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(NotFoundError, not_found_error_handler)
    app.add_exception_handler(ConflictError, conflict_error_handler)
