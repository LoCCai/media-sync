"""Fail-closed deployment gate for the embedded MediaCrawler console."""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse

MEDIACRAWLER_LICENSE_REQUIRED_CODE: Final = "license_acknowledgement_required"
_HTTP_METHODS: Final = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")


def mediacrawler_license_required_response() -> JSONResponse:
    """Return the one bounded response used by every gated HTTP route."""

    return JSONResponse(
        status_code=503,
        content={"detail": MEDIACRAWLER_LICENSE_REQUIRED_CODE},
        headers={"Cache-Control": "no-store"},
    )


def create_mediacrawler_license_gate_app() -> FastAPI:
    """Return an inert ASGI surface that cannot start the upstream crawler."""

    app = FastAPI(
        title="MediaCrawler license gate",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.api_route("/", methods=list(_HTTP_METHODS), include_in_schema=False)
    @app.api_route("/{path:path}", methods=list(_HTTP_METHODS), include_in_schema=False)
    async def license_required(path: str = "") -> JSONResponse:
        del path
        return mediacrawler_license_required_response()

    @app.websocket("/{path:path}")
    async def websocket_license_required(websocket: WebSocket, path: str) -> None:
        del path
        await websocket.close(code=4403, reason=MEDIACRAWLER_LICENSE_REQUIRED_CODE)

    return app


__all__ = [
    "MEDIACRAWLER_LICENSE_REQUIRED_CODE",
    "create_mediacrawler_license_gate_app",
    "mediacrawler_license_required_response",
]
