# Owner: Hiba
"""FastAPI application entrypoint."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, chat, cms, tenants, widgets


def _widget_dist_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "frontend" / "widget" / "dist"


def create_app(widget_dist_dir: Path | None = None) -> FastAPI:
    """Create and configure the Concierge API application."""
    app = FastAPI(title="Week 8 Concierge API")

    app.include_router(tenants.router)
    app.include_router(cms.router)
    app.include_router(widgets.router)
    app.include_router(chat.router)
    app.include_router(auth.router)

    dist_dir = widget_dist_dir or _widget_dist_dir()
    if dist_dir.exists():
        app.mount(
            "/",
            StaticFiles(directory=str(dist_dir), html=True),
            name="widget_frontend",
        )

    return app


app = create_app()
