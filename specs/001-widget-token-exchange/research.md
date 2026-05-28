# Phase 0: Research

Three technical choices were unresolved at the start of planning. Each is documented below in **Decision / Rationale / Alternatives** form. None turned out to be blockers; all resolve to standard, simple options consistent with the constitution.

## Research 1 — JWT library

**Decision**: PyJWT 2.x.

**Rationale**:
- Already listed in [pyproject.toml](../../pyproject.toml) (`pyjwt`); zero new dependencies.
- Maintained, security-audited, used by FastAPI tutorials and the broader Python community.
- HS256 + dict-of-claims fits FR-004 (cryptographic signing) and FR-005 (origin binding) without any extra wrapper.
- The `jwt.encode` / `jwt.decode` surface is small enough that the entire JWT lifecycle can live in `app/services/widget_service.py` without an additional helper class.

**Alternatives considered**:
- `python-jose` — broader algorithm coverage we don't need; not currently in the dependency set; would be a new transitive dep.
- `authlib` — overkill (full OAuth/OpenID toolkit); we issue one JWT type, not an auth framework.
- Hand-rolled HMAC token — Principle VII rejects rolling crypto when a maintained library is already in `pyproject.toml`.

## Research 2 — Rate-limiter implementation

**Decision**: In-process token-bucket counter per worker process for this phase, with a documented seam to swap in a Redis-backed limiter once cross-worker accuracy is required.

**Rationale**:
- FR-018 mandates runtime-configurable limits but does not mandate cross-worker accuracy. With the default Uvicorn worker count for dev (1) and the modest planned production worker count (2–4), per-worker counters provide an acceptable approximation that is consistent across requests served by the same worker. An attacker exploiting worker affinity to evade the limit would still pay the per-widget limit, which is enforced regardless.
- An in-process limiter has zero infrastructure dependency, ships with the FastAPI app, and is easy to reason about (single struct: `dict[(scope_key), TokenBucket]`).
- The seam: `WidgetTokenService` calls a `RateLimiter` Protocol (`async def check(self, scope_key: str) -> bool`); the in-process implementation is the default, and a Redis implementation can be added later by Hiba's slice (which already runs Redis for session memory) without changing this feature.

**Alternatives considered**:
- **Redis-backed from day one** (e.g., via `redis-py` `INCR` + TTL): cross-worker accurate but introduces a dependency on Hiba's Redis being provisioned for this feature in this phase. Constitution Principle VII (smallest change) says no.
- **Reverse-proxy rate limiting** (nginx `limit_req`, Cloud Load Balancer): pushes the decision out of the app and breaks FR-017 (indistinguishable rate-limited response shape) because reverse-proxy 429s have a different body than FastAPI errors.
- **No limiter, defer entirely to Hiba's slice**: rejected during clarification (Q1 → B); the consequence is that this feature owns the baseline.

## Research 3 — HMAC salt provisioning for log identifiers

**Decision**: A separate environment variable `WIDGET_LOG_SALT` (32+ random bytes, base64-encoded), distinct from `WIDGET_JWT_SECRET`. Loaded once at app start; never rotated automatically.

**Rationale**:
- FR-020 requires hashed widget identifiers and IPs in refusal logs so identifiers are not reversible offline.
- Using the JWT signing secret as the log salt would couple two unrelated security surfaces — rotating the signing key (a security operation) would silently break log correlation. Distinct secrets per purpose is the textbook hygiene rule.
- A second env var is one line in `.env.example` and one line in `app/config.py`. Both are inside Amer's slice.
- Rotation: when the salt is rotated, historical hashed log values stop correlating to current ones. That is acceptable because the salt's purpose is to prevent offline rainbow-table attacks against logs, not to enable long-term identifier tracking. Rotation cadence is a platform-operator decision and out of scope here.

**Alternatives considered**:
- **Reuse `WIDGET_JWT_SECRET`**: convenient but couples unrelated security operations (rejected, see above).
- **Hash without a salt** (plain SHA-256): widget identifiers are UUIDs from a public namespace and have low entropy when an attacker has captured logs — they can re-hash candidate UUIDs and match. Unsalted hashing fails Principle V's redaction intent.
- **Per-tenant salt**: would let the platform support tenant-controlled log opacity, but no requirement asks for it; Principle VII rejects.

## Other items briefly considered but no research required

- **Indistinguishable failure response shape** — already fully specified in spec FR-007. No design freedom remains; implementation is mechanical.
- **JWT claim names** — already specified in spec (`tenant_id`, `widget_id`, `origin`, `session_id`, `exp`) and CONTRACT.md §2.9.
- **Token TTL** — fixed at 15 minutes per spec FR-009; surfaced as `WIDGET_TOKEN_TTL_SECONDS` env var to allow platform-level adjustment (FR-018 already mandates runtime configurability for rate limits, and we get this one for free without violating Principle VII).
- **Frontend test framework** — vitest, the standard pairing with Vite. Adding `vitest`, `@vitest/ui`, and `jsdom` as devDeps in `frontend/widget/package.json` is the minimal addition. Not a research question, just a tool choice.
