"""Content-safe errors scoped to document/version routes."""

from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, SQLAlchemyError


class DocumentRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def safe_handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422, content={"detail": "Invalid document version request"}
                )
            except DBAPIError as error:
                if getattr(error.orig, "sqlstate", None) in {"55P03", "40P01", "57014", "23505"}:
                    return JSONResponse(
                        status_code=409, content={"detail": "Document version operation conflict"}
                    )
                return JSONResponse(
                    status_code=500, content={"detail": "Document persistence unavailable"}
                )
            except (ResponseValidationError, ValidationError, SQLAlchemyError):
                return JSONResponse(
                    status_code=500, content={"detail": "Document persistence unavailable"}
                )

        return safe_handler
