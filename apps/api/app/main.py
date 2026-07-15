from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.errors import AppError, app_error_handler


def create_app() -> FastAPI:
    app = FastAPI(title="paper-diff API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(router)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
