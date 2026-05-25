# Owner: Hiba
"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.routes import chat, cms, tenants, widgets


def create_app() -> FastAPI:
    """Create and configure the Concierge API application."""
    app = FastAPI(title="Week 8 Concierge API")

    app.include_router(tenants.router)
    app.include_router(cms.router)
    app.include_router(widgets.router)
    app.include_router(chat.router)

    return app


app = create_app()
