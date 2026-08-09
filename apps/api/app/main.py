# paper-diff — LaTeX paper version diff + accept merge + Docker compile.
# Copyright (C) paper-diff contributors.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the LICENSE
# file in the repository root for the full text (AGPL-3.0-or-later).

from __future__ import annotations

import logging
import traceback
from contextlib import asynccontextmanager
from collections.abc import Callable
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.composition.container import default_container
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.storage.admin import StorageAdmin
from app.storage.errors import (
    InvalidStorageKey,
    StorageCapabilityUnavailable,
    StorageConflict,
    StorageError,
    StorageNotFound,
    StorageQuotaExceeded,
    StorageUnavailable,
)

if TYPE_CHECKING:
    from app.composition.container import AppContainer

ContainerResolver = Callable[[Request], "AppContainer"]

logger = logging.getLogger("paper_diff")


def clear_workspace_if_enabled(application: FastAPI | None = None) -> None:
    """Clear the configured storage namespace when explicitly enabled."""
    injected = getattr(getattr(application, "state", None), "container", None)
    resolver = getattr(getattr(application, "state", None), "container_resolver", None)
    if injected is None and resolver is not None:
        logger.warning("startup clear skipped for request-scoped container resolver")
        return
    settings = injected.settings if injected is not None else get_settings()
    if not settings.clear_workspace_on_startup:
        logger.info(
            "workspace cleanup skipped (PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP=false)"
        )
        return
    try:
        factory = injected.storage if injected is not None else default_container(settings).storage
        removed = StorageAdmin(factory).clear_namespace()
    except StorageCapabilityUnavailable as exc:
        logger.warning("%s", exc)
        return
    logger.info("cleared storage namespace %s (%d entries)", factory.namespace, removed)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    clear_workspace_if_enabled(_app)
    yield


def create_app(
    container: AppContainer | None = None,
    *,
    container_resolver: ContainerResolver | None = None,
) -> FastAPI:
    app = FastAPI(title="paper-diff API", version="0.2.0", lifespan=lifespan)
    app.state.container = container
    app.state.container_resolver = container_resolver
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(AppError, app_error_handler)

    @app.exception_handler(StorageError)
    async def storage_error_handler(_request: Request, exc: StorageError):
        if isinstance(exc, InvalidStorageKey):
            status, code = 400, "INVALID_STORAGE_KEY"
        elif isinstance(exc, StorageNotFound):
            status, code = 404, "FILE_NOT_FOUND"
        elif isinstance(exc, StorageConflict):
            status, code = 409, "STORAGE_CONFLICT"
        elif isinstance(exc, StorageQuotaExceeded):
            status, code = 413, "STORAGE_QUOTA_EXCEEDED"
        elif isinstance(exc, StorageCapabilityUnavailable):
            status, code = 501, "STORAGE_CAPABILITY_UNAVAILABLE"
        elif isinstance(exc, StorageUnavailable):
            status, code = 503, "STORAGE_UNAVAILABLE"
        else:
            status, code = 500, "STORAGE_ERROR"
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": str(exc) or type(exc).__name__,
                    "details": None,
                    "request_id": None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Avoid masking FastAPI/Starlette HTTPException subclasses if any slip in
        tb = traceback.format_exc()
        logger.exception("unhandled error %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": str(exc) or type(exc).__name__,
                    "details": {
                        "type": type(exc).__name__,
                        "path": request.url.path,
                        "traceback": tb[-4000:],
                    },
                    "request_id": None,
                }
            },
        )

    app.include_router(router)

    @app.get("/health")
    def health():
        settings = get_settings()
        provider = (settings.agent_provider or "off").strip().lower()
        if provider == "http" and (settings.agent_api_key or settings.agent_http_url):
            agent_provider = "http"
        elif provider == "stub":
            agent_provider = "stub"
        else:
            agent_provider = "off"
        return {
            "ok": True,
            "status": "ok",
            "version": settings.api_version,
            "model": "v2",
            "agent_provider": agent_provider,
            "clear_workspace_on_startup": settings.clear_workspace_on_startup,
        }

    return app


app = create_app()
