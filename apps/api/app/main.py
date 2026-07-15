import logging
import shutil
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler

logger = logging.getLogger("paper_diff")


def clear_workspace_if_enabled() -> None:
    """Remove project trees under workspace_root when clear_workspace_on_startup is true."""
    settings = get_settings()
    if not settings.clear_workspace_on_startup:
        logger.info(
            "workspace cleanup skipped (PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP=false)"
        )
        return
    root = settings.workspace_root
    try:
        root = root.resolve()
    except OSError:
        root = settings.workspace_root
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
        logger.info("workspace root created: %s", root)
        return
    # Only wipe if path looks like a workspace dir (avoid accidental home wipe)
    name = root.name.lower()
    if name not in ("projects", "workspace", "workspaces", "data") and "project" not in name:
        # Still allow default ./data/projects and custom paths containing paper-diff
        if "paper-diff" not in str(root).lower() and "paper_diff" not in str(root).lower():
            logger.warning(
                "refusing to clear workspace_root=%s (name not recognized as dev workspace); "
                "set path under *projects* or containing paper-diff, or clear manually",
                root,
            )
            return
    removed = 0
    for child in list(root.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
            removed += 1
        except OSError as e:
            logger.warning("failed to remove %s: %s", child, e)
    logger.info("cleared workspace on startup: %s (%d entries)", root, removed)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    clear_workspace_if_enabled()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="paper-diff API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(AppError, app_error_handler)

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
        return {
            "ok": True,
            "status": "ok",
            "version": settings.api_version,
            "model": "v2",
        }

    return app


app = create_app()
