# Owner: Amer
"""Seed a complete demo fixture in one call.

Populates 2 tenants × 2 CMS pages × 3 leads × 2 escalations, plus a widget
config and a `tenant_admin` per tenant. Idempotent: re-running is a no-op on
existing rows (matched by unique constraint: tenant name, admin email,
tenant_id-scoped widget config, tenant_id+slug for CMS pages, tenant+intent
for leads, conversation for escalations).

Usage:
    python -m scripts.seed_demo

Then sign in to the admin UI as either of:
    boss@acme.example      / DemoBoss123    (tenant_manager, Tenant A)
    admin@acme.example     / DemoAdmin123   (tenant_admin,   Tenant A)
    admin@globex.example   / DemoAdmin123   (tenant_admin,   Tenant B)

Quickstart §2 references this script; the bare `seed_tenants` / `seed_admin` /
`seed_widget_config` scripts still exist for piecewise dev workflows.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select

from app.db.models import (
    CmsPage,
    Conversation,
    EscalationTicket,
    Lead,
    WidgetConfig,
)
from app.db.session import get_sessionmaker
from app.infra.password import hash_password
from app.rag.ingest import sync_cms_page_index
from app.repositories.admin_user_repo import AdminUserRepository
from scripts.seed_tenants import seed_demo_tenants_with_session

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemoAdmin:
    email: str
    password: str
    role: str


@dataclass(frozen=True)
class DemoWidget:
    widget_id: UUID
    origins: tuple[str, ...]
    greeting: str


@dataclass(frozen=True)
class DemoTenantPlan:
    name: str
    widget: DemoWidget
    admins: tuple[DemoAdmin, ...]
    cms_pages: tuple[tuple[str, str, str], ...]  # (title, slug, body)
    leads: tuple[tuple[str, str, str], ...]  # (name, contact, intent)
    escalations: tuple[tuple[str, str], ...]  # (session_id, reason)


DEMO_PLAN: tuple[DemoTenantPlan, ...] = (
    DemoTenantPlan(
        name="Tenant A",
        widget=DemoWidget(
            widget_id=UUID("9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d"),
            origins=("http://localhost:5173",),
            greeting="Hi! I'm the Tenant A concierge — ask about alpha-cookies.",
        ),
        admins=(
            DemoAdmin(
                email="boss@acme.example",
                password="DemoBoss123",
                role="tenant_manager",
            ),
            DemoAdmin(
                email="admin@acme.example",
                password="DemoAdmin123",
                role="tenant_admin",
            ),
        ),
        cms_pages=(
            (
                "Opening Hours",
                "opening-hours",
                "Our alpha-cookies bakery is open Monday-Friday 8am-6pm. "
                "Weekends 9am-4pm. Closed on public holidays.",
            ),
            (
                "Pricing",
                "pricing",
                "Alpha-cookies start at $12/dozen. Bulk orders over 100 dozen "
                "qualify for a 15% wholesale discount. Email pricing@acme.example.",
            ),
        ),
        leads=(
            ("Jane Buyer", "jane@example.com", "pricing inquiry"),
            ("Carl Wholesale", "carl@example.com", "wholesale order"),
            ("Anonymous", "555-0100", "callback request"),
        ),
        escalations=(
            ("demo-a-esc-1", "visitor asked to speak to a human about a refund"),
            ("demo-a-esc-2", "complex custom-order question outside FAQ scope"),
        ),
    ),
    DemoTenantPlan(
        name="Tenant B",
        widget=DemoWidget(
            widget_id=UUID("4b6c8e0f-2d1a-4e9b-8a3f-7c5b9d2e1a0c"),
            origins=("http://localhost:5174",),
            greeting="Hello! I'm the Tenant B concierge — ask about bravo-pastries.",
        ),
        admins=(
            DemoAdmin(
                email="admin@globex.example",
                password="DemoAdmin123",
                role="tenant_admin",
            ),
        ),
        cms_pages=(
            (
                "Locations",
                "locations",
                "Bravo-pastries operates two locations: downtown and the airport. "
                "Both serve fresh croissants daily.",
            ),
            (
                "Catering Menu",
                "catering",
                "Bravo-pastries catering covers events from 10 to 500 guests. "
                "Menus include vegan and gluten-free options.",
            ),
        ),
        leads=(
            ("Ravi Event", "ravi@example.com", "catering inquiry"),
            ("Sam Visitor", "sam@example.com", "general inquiry"),
            ("Pat Caller", "555-0200", "callback request"),
        ),
        escalations=(
            ("demo-b-esc-1", "visitor reported allergic reaction; needs human contact"),
            ("demo-b-esc-2", "wedding catering quote out of standard menu"),
        ),
    ),
)


async def _seed_admins(
    session, *, tenant_id: UUID, admins: tuple[DemoAdmin, ...]
) -> list[tuple[str, str]]:
    """Insert/refresh tenant admins; returns (email, state) pairs.

    The seeder owns the demo credentials — if the email already exists, its
    password / role / status / tenant binding are rewritten to match the
    DemoAdmin plan. Without this, prior dev seeding leaves rows whose
    password no longer matches the quickstart docs and login fails opaquely.
    """
    repo = AdminUserRepository(session)
    results: list[tuple[str, str]] = []
    for admin in admins:
        existing = await repo.get_by_email(admin.email)
        if existing is None:
            await repo.create(
                tenant_id=tenant_id,
                email=admin.email,
                password_hash=hash_password(admin.password),
                role=admin.role,
            )
            results.append((admin.email, "created"))
            continue
        existing.password_hash = hash_password(admin.password)
        existing.role = admin.role
        existing.status = "active"
        existing.tenant_id = tenant_id
        results.append((admin.email, "refreshed"))
    return results


async def _seed_widget(session, *, tenant_id: UUID, widget: DemoWidget) -> str:
    """Ensure exactly one widget_configs row points the demo widget_id at the
    demo tenant. Returns one of: 'created', 'exists', 'rebound', 'reset'.

    - created: fresh insert.
    - exists:  row already present with the right (tenant_id, widget_id).
    - rebound: row had our widget_id but the wrong tenant_id (leftover from
      prior dev runs) — rebind it to the demo tenant so the documented
      widget_id keeps working.
    - reset:   row exists for this tenant but with a different widget_id —
      replace it with the documented one.
    """
    by_widget_id_q = await session.execute(
        select(WidgetConfig).where(WidgetConfig.widget_id == widget.widget_id)
    )
    by_widget_id = by_widget_id_q.scalar_one_or_none()
    by_tenant_q = await session.execute(
        select(WidgetConfig).where(WidgetConfig.tenant_id == tenant_id)
    )
    by_tenant = by_tenant_q.scalar_one_or_none()

    if by_widget_id is not None and by_widget_id.tenant_id == tenant_id:
        return "exists"

    if by_widget_id is not None:
        if by_tenant is not None and by_tenant.id != by_widget_id.id:
            await session.delete(by_tenant)
            await session.flush()
        by_widget_id.tenant_id = tenant_id
        by_widget_id.allowed_origins_json = list(widget.origins)
        by_widget_id.greeting = widget.greeting
        by_widget_id.enabled = True
        return "rebound"

    if by_tenant is not None:
        by_tenant.widget_id = widget.widget_id
        by_tenant.allowed_origins_json = list(widget.origins)
        by_tenant.greeting = widget.greeting
        by_tenant.enabled = True
        return "reset"

    session.add(
        WidgetConfig(
            id=uuid4(),
            tenant_id=tenant_id,
            widget_id=widget.widget_id,
            allowed_origins_json=list(widget.origins),
            theme_json={},
            greeting=widget.greeting,
            enabled=True,
        )
    )
    return "created"


async def _seed_cms_pages(
    session,
    *,
    tenant_id: UUID,
    pages: tuple[tuple[str, str, str], ...],
) -> int:
    """Insert CMS pages keyed by (tenant_id, slug). Returns count of new rows."""
    created = 0
    for title, slug, body in pages:
        existing = await session.execute(
            select(CmsPage).where(
                CmsPage.tenant_id == tenant_id, CmsPage.slug == slug
            )
        )
        page = existing.scalar_one_or_none()
        if page is None:
            page = CmsPage(
                id=uuid4(),
                tenant_id=tenant_id,
                title=title,
                slug=slug,
                body=body,
                status="published",
                created_by="seed:demo",
            )
            session.add(page)
            await session.flush()
            created += 1

        await sync_cms_page_index(
            session,
            tenant_id=tenant_id,
            page_id=page.id,
            text=page.body,
            source_title=page.title,
            source_url=page.source_url,
            status=page.status,
        )
    return created


async def _seed_leads(
    session,
    *,
    tenant_id: UUID,
    leads: tuple[tuple[str, str, str], ...],
) -> int:
    """Insert leads keyed by (tenant_id, contact, intent). Returns new-row count."""
    created = 0
    for name, contact, intent in leads:
        existing = await session.execute(
            select(Lead).where(
                Lead.tenant_id == tenant_id,
                Lead.contact == contact,
                Lead.intent == intent,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        session.add(
            Lead(
                id=uuid4(),
                tenant_id=tenant_id,
                name=name,
                contact=contact,
                intent=intent,
                status="captured",
            )
        )
        created += 1
    return created


async def _seed_escalations(
    session,
    *,
    tenant_id: UUID,
    widget_id: UUID,
    escalations: tuple[tuple[str, str], ...],
) -> int:
    """Each escalation needs a parent conversation; both keyed by session_id.

    Idempotency: conversation matched by (tenant_id, session_id) unique
    constraint; if its conversation exists with any escalation row already, skip.
    """
    created = 0
    for session_id, reason in escalations:
        conv_row = await session.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.session_id == session_id,
            )
        )
        conversation = conv_row.scalar_one_or_none()
        if conversation is None:
            conversation = Conversation(
                id=uuid4(),
                tenant_id=tenant_id,
                widget_id=widget_id,
                session_id=session_id,
                status="open",
            )
            session.add(conversation)
            await session.flush()
        existing = await session.execute(
            select(EscalationTicket).where(
                EscalationTicket.tenant_id == tenant_id,
                EscalationTicket.conversation_id == conversation.id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        session.add(
            EscalationTicket(
                id=uuid4(),
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                reason=reason,
                status="open",
            )
        )
        created += 1
    return created


async def seed_demo() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            tenants = await seed_demo_tenants_with_session(
                session, actor_id="seed:demo"
            )
            name_to_id = {t.name: t.tenant_id for t in tenants}

            for plan in DEMO_PLAN:
                tenant_id = name_to_id.get(plan.name)
                if tenant_id is None:
                    LOGGER.warning("tenant %s not found after seed; skipping", plan.name)
                    continue

                widget_state = await _seed_widget(
                    session, tenant_id=tenant_id, widget=plan.widget
                )
                admin_results = await _seed_admins(
                    session, tenant_id=tenant_id, admins=plan.admins
                )
                cms_new = await _seed_cms_pages(
                    session, tenant_id=tenant_id, pages=plan.cms_pages
                )
                leads_new = await _seed_leads(
                    session, tenant_id=tenant_id, leads=plan.leads
                )
                esc_new = await _seed_escalations(
                    session,
                    tenant_id=tenant_id,
                    widget_id=plan.widget.widget_id,
                    escalations=plan.escalations,
                )

                LOGGER.info(
                    "%s (%s): widget=%s admins=%s cms=+%d leads=+%d escalations=+%d",
                    plan.name,
                    tenant_id,
                    widget_state,
                    ", ".join(
                        f"{email}({state})" for email, state in admin_results
                    ),
                    cms_new,
                    leads_new,
                    esc_new,
                )

            await session.commit()
        except Exception:
            await session.rollback()
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a complete demo fixture.")
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(seed_demo())


if __name__ == "__main__":
    main()
