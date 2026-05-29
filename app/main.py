# Owner: Hiba
"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.routes import (
    admin_auth,
    admin_invites,
    chat,
    cms,
    escalations,
    leads,
    tenants,
    widgets,
)


def create_app() -> FastAPI:
    """Create and configure the Concierge API application."""
    app = FastAPI(title="Week 8 Concierge API")

    app.include_router(tenants.router)
    app.include_router(tenants.platform_router)
    app.include_router(cms.router)
    app.include_router(widgets.router)
    app.include_router(chat.router)
    app.include_router(admin_auth.router)
    app.include_router(admin_invites.router)
    app.include_router(leads.router)
    app.include_router(escalations.router)

    return app


app = create_app()
