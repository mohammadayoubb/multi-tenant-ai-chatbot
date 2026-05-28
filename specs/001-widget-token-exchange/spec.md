# Feature Specification: Secure Widget Token Exchange

**Feature Branch**: `001-widget-token-exchange`
**Created**: 2026-05-26
**Status**: Draft
**Input**: User description: "Implement secure widget token exchange for the embeddable widget. Server validates widget_id + origin, issues a short-lived signed token containing tenant identity. Token stored in browser memory only. Failure responses do not leak which check failed."

## Clarifications

### Session 2026-05-26

- Q: How should this feature handle rate limiting on the token issuance endpoint? → A: This feature owns a per-IP and per-widget rate baseline at the token endpoint; the platform-level per-tenant limiter layers on top.
- Q: When a tenant admin removes an origin or disables a widget mid-flight, should already-issued tokens be revoked or left to expire naturally? → A: Defer revocation; the 15-minute token lifetime is the sole mitigation. Re-evaluate on first tenant request for explicit revocation or first incident showing 15 minutes is too long.
- Q: What observability does the token endpoint commit to? → A: Counters (FR-014) plus a structured log entry per refusal with internal reason bucket, plus one distributed trace span per token request (success and failure). Logs use hashed widget identifier and hashed source IP — no raw visitor PII.
- Q: How are subdomains treated when matching an origin against the allowlist? → A: Strict exact-host matching. `https://customer-site.example` does NOT match `https://www.customer-site.example`. Tenants list every subdomain they use. No wildcard syntax.
- Q: How strict is the timing-side-channel guarantee on refusals? → A: Minimum baseline — every refusal path always performs the widget lookup before returning, so all refusal causes pay the same DB cost. No constant-time crypto or response padding committed in this phase.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Visitor on an authorized host site can chat with the tenant's agent (Priority: P1)

A visitor lands on a tenant's public website that has the Concierge widget embedded. The widget appears on the page, fetches its session credential from the platform, and becomes ready to accept a chat message — all without the visitor doing anything other than loading the page.

**Why this priority**: This is the entire purpose of the widget. Without successful token exchange, no chat is possible on any tenant site; every other widget and chat feature is blocked.

**Independent Test**: Embed the widget on a host page whose origin is configured as an allowed origin for a known active widget. Open the page in a browser. The widget should reach a chat-ready state (visible chat input) within one second of page load, with no error states shown.

**Acceptance Scenarios**:

1. **Given** a widget configured with allowed origins including `https://customer-site.example`, **When** a visitor loads `https://customer-site.example/page-with-widget`, **Then** the widget reaches the chat-ready state and the visitor can type a message.
2. **Given** the widget is in chat-ready state, **When** the visitor inspects browser storage (cookies, localStorage, sessionStorage), **Then** no widget session credential is visible in any persistent storage.
3. **Given** an active tenant with at least one widget, **When** the widget loader script runs on the page, **Then** the session credential is bound to that specific tenant (not any other tenant on the platform).

---

### User Story 2 - Token requests from unauthorized origins are refused (Priority: P1)

An attacker who has copied a tenant's widget identifier and embeds the loader on a site they control attempts to obtain a session credential from the platform. The platform refuses to issue one. The same attacker, who has guessed a non-existent widget identifier, also receives a refusal — indistinguishable from the previous refusal so they cannot tell which guess was closer.

**Why this priority**: This is the security guarantee that makes widget identifiers safe to publish in HTML. Without it, anyone who views the page source of a tenant's site can issue tokens from arbitrary origins — defeating the entire tenant-isolation model on the visitor side.

**Independent Test**: Attempt token exchange from three scenarios — (a) a valid widget identifier from an origin not in its allowlist, (b) an invalid widget identifier from any origin, (c) a valid widget identifier whose tenant is currently suspended. All three must fail and the response payload must be byte-identical (or differ only in non-distinguishing fields like a request timestamp).

**Acceptance Scenarios**:

1. **Given** widget `W` whose allowlist is `[https://customer-site.example]`, **When** a token exchange request arrives with origin `https://attacker.example`, **Then** the platform returns a generic failure and no token is issued.
2. **Given** widget identifier `W'` that does not exist in the platform, **When** a token exchange request arrives, **Then** the platform returns the same generic failure shape.
3. **Given** widget `W` belongs to a suspended tenant, **When** a token exchange request arrives from an allowlisted origin, **Then** the platform returns the same generic failure shape.
4. **Given** widget `W` belongs to an active tenant but the widget itself is disabled, **When** a token exchange request arrives, **Then** the platform returns the same generic failure shape.
5. **Given** any of the failure cases above, **When** the response body and HTTP status of all four are compared, **Then** they reveal no information about which check failed.

---

### User Story 3 - Tokens are short-lived and visitor-bound (Priority: P2)

A token issued to a visitor on a tenant's site is valid for a brief window only. If the visitor leaves the page open and returns hours later, the token has expired and a new one must be issued (which re-runs the origin check). A token captured by a network observer cannot be replayed indefinitely.

**Why this priority**: Caps the blast radius of any token leakage. If a malicious browser extension or network observer captures a token, the window of misuse is bounded.

**Independent Test**: Obtain a token. Wait until its embedded expiration passes. Present the expired token to any downstream service that consumes it (e.g., chat) — the service rejects it.

**Acceptance Scenarios**:

1. **Given** a token issued at time T, **When** the current time exceeds T + the configured short-lived window, **Then** any service consuming the token rejects it as expired.
2. **Given** the same token, **When** the visitor closes the browser and reopens the host page, **Then** a new token is fetched (the old one is not recovered from any persistent store).

---

### Edge Cases

- **Replay from a different origin**: A token issued for origin A cannot be replayed by a script running on origin B — the token's bound origin is part of the issuance record and downstream consumers can compare.
- **Origin with query string or fragment**: Allowlist comparison ignores path, query, and fragment; matches scheme + host + port exactly.
- **Origin case sensitivity**: Host portion is matched case-insensitively (DNS is case-insensitive); scheme and port are exact.
- **Subdomains**: Treated as distinct origins. An allowlist entry of `https://customer-site.example` does not authorize `https://www.customer-site.example`, `https://app.customer-site.example`, or any other subdomain. This shifts a small admin burden onto tenants (Phase 4 admin UI lets them enumerate subdomains) in exchange for closing the subdomain-takeover oracle attack vector.
- **Tenant transitions to erasing or erased mid-flow**: Any subsequent token request is refused with the same generic failure as other rejection cases.
- **Widget disabled or origin removed by tenant admin after a token has been issued**: Existing tokens remain valid until natural expiration; future token requests are refused immediately. This is a conscious deferral — no revocation mechanism in this phase. The 15-minute token lifetime (FR-009) is the sole mitigation. Re-evaluate this trade-off the first time either (a) a tenant explicitly requests immediate revocation, or (b) an incident shows the 15-minute window is too long.
- **Clock skew between visitor browser and platform**: Expiration is evaluated server-side at the consuming service; visitor clock is not authoritative.
- **Allowlist is empty**: No origin can succeed; equivalent to widget disabled.
- **Visitor refreshes page repeatedly**: Each refresh issues a new token, subject to the per-IP baseline (FR-015). Legitimate shared-IP scenarios (corporate NAT, mobile carrier proxy) may occasionally hit the baseline; affected visitors see the same neutral "Widget unavailable" indicator and the tenant can request an elevated limit out-of-band.
- **Gross timing-side-channel on refusals**: Mitigated by FR-008a — the widget-configuration lookup is always performed before any refusal returns, so unknown-widget and origin-mismatch responses pay the same DB cost. Sub-millisecond timing residuals from later validation steps remain measurable in principle; full constant-time hardening (constant-time comparison, fixed-size response padding, fixed minimum latency) is explicitly deferred to a future feature triggered by a red-team finding or an audit requirement.

## Requirements *(mandatory)*

### Functional Requirements

**Issuance gating**

- **FR-001**: The platform MUST refuse to issue a session credential unless the requesting widget identifier corresponds to an existing, enabled widget configuration whose owning tenant is in the active state.
- **FR-002**: The platform MUST refuse to issue a session credential unless the origin presented in the request exactly matches one of the allowed origins configured for that widget. Matching rules: scheme exact, port exact, host exact (case-insensitive); path / query / fragment ignored. **No subdomain rollup, no wildcard syntax** — `https://customer-site.example` does not match `https://www.customer-site.example`; tenants must list each subdomain they use.
- **FR-003**: The platform MUST embed the tenant identity in the issued credential using server-side state (looked up from the widget configuration), NEVER from any field supplied by the requesting client.
- **FR-004**: The platform MUST cryptographically sign every issued credential such that any modification by the holder is detectable by downstream services that consume it.
- **FR-005**: The platform MUST bind every issued credential to the specific origin from which it was requested, so downstream services can detect cross-origin replay.
- **FR-006**: The platform MUST generate a fresh, unique session identifier per credential issuance; the same browser session is not reused across reloads of the host page.

**Failure handling**

- **FR-007**: The platform MUST return responses for all rejection causes (unknown widget, origin not in allowlist, tenant not active, widget disabled) that are indistinguishable from one another by external observers — same HTTP status, same response body shape, same fields, same headers (except those legitimately varying like request timestamp).
- **FR-008**: The platform MUST NOT include in any rejection response any information about whether the widget identifier existed, the tenant state, or the allowlist contents.
- **FR-008a**: The platform MUST always perform the widget-configuration lookup before returning any refusal, regardless of which check ultimately rejects the request. This ensures every refusal path (unknown widget, origin not allowlisted, widget disabled, tenant not active, rate limit hit) incurs the same database-lookup cost, denying an attacker a gross timing-side-channel signal. Sub-millisecond timing residuals from later checks are out of scope in this phase; constant-time comparison and response padding are not committed.

**Token lifetime**

- **FR-009**: Every issued credential MUST expire within a short window from issuance (default: 15 minutes).
- **FR-010**: Downstream services consuming the credential MUST reject any credential whose expiration time has passed.

**Browser storage discipline (visitor side)**

- **FR-011**: The embedded widget MUST hold the session credential only in volatile in-memory storage that does not survive page reload or tab close.
- **FR-012**: The embedded widget MUST NOT write the session credential to cookies, localStorage, sessionStorage, IndexedDB, or any other browser-persisted store.
- **FR-013**: If credential acquisition fails for any reason, the widget MUST display a single neutral failure indicator ("Widget unavailable") and MUST NOT expose the chat input or any other interactive element to the visitor.

**Auditability**

- **FR-014**: The platform MUST be able to count token issuance and rejection events per tenant for cost and rate-limit accounting, without storing any visitor-identifying information in the count.
- **FR-020**: The platform MUST emit a structured log entry for every token-issuance refusal containing: timestamp, hashed widget identifier, hashed source IP, source origin, and an internal rejection-reason bucket (unknown-widget / origin-not-allowlisted / widget-disabled / tenant-not-active / rate-limited-per-ip / rate-limited-per-widget). The hashing function MUST use a per-deployment salt so identifiers cannot be reversed offline.
- **FR-021**: Logs emitted by this feature MUST NOT contain unhashed visitor IP addresses, unhashed widget identifiers, raw tokens, the JWT signing secret, or any other visitor-identifying or secret material. Origin (a host name already revealed by the client) is acceptable.
- **FR-022**: The platform MUST emit exactly one distributed trace span per token-issuance request (success or failure) carrying: outcome (issued / refused), latency, source origin, hashed widget identifier, and — on success only — the resolved tenant identity. The trace span MUST participate in the platform's shared trace context so the request can be correlated across services.
- **FR-023**: Internal logs and traces MAY record the specific rejection-reason bucket even though the response to the client MUST NOT distinguish causes (FR-007); the indistinguishability guarantee is scoped to external observers of the response, not to operations.

**Abuse resistance**

- **FR-015**: The platform MUST enforce a per-IP request-rate baseline on the token issuance endpoint that applies before any widget identifier or origin is resolved, so an attacker cannot use the endpoint to cheaply enumerate widget identifiers or origins.
- **FR-016**: The platform MUST enforce a per-widget request-rate baseline on the token issuance endpoint so a single widget cannot be used as an oracle for high-volume origin probing.
- **FR-017**: Responses to rate-limited requests MUST follow the same indistinguishability rules as validation refusals (FR-007); external observers MUST NOT be able to determine whether a block was caused by rate limiting versus an unknown widget, an unallowed origin, a disabled widget, or a non-active tenant.
- **FR-018**: Both rate baselines (per-IP and per-widget) MUST be platform-configurable at runtime so the platform owner can tune them in response to observed abuse patterns without redeploying.
- **FR-019**: The per-tenant rate limit operated by the tenancy platform (CONTRACT.md §2.6) MUST continue to apply on top of the per-IP and per-widget baselines defined here; the endpoint-level baselines are additive defense, not a replacement.

### Key Entities

- **Widget Configuration**: A per-tenant record that identifies a deployable widget, the tenant that owns it, the list of website origins authorized to obtain session credentials for it, and whether the widget is currently enabled.
- **Widget Session Credential**: A short-lived, tamper-evident token that proves a visitor's browser reached the platform from an authorized origin for a specific widget owned by a specific tenant. Contains tenant identity, widget identity, originating site, session identity, and expiration. Holds no visitor personally identifying information.
- **Tenant Lifecycle State**: The active/suspended/erasing/erased state of a tenant. Only `active` tenants may have new session credentials issued for their widgets.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of credential issuance requests are gated by both widget existence and origin allowlist checks; no code path bypasses either gate (verified by integration tests and a red-team probe).
- **SC-002**: An attacker scripting against the token endpoint with arbitrary widget identifiers, arbitrary origins, or exceeding the per-IP / per-widget rate baselines receives byte-identical failure responses across every rejection cause (verified by automated comparison test covering all refusal scenarios, including rate-limited requests).
- **SC-003**: A visitor loading a host page whose origin is allowlisted sees the widget reach the chat-ready state within 1 second on a standard residential connection (95th percentile across geographic regions in the test suite).
- **SC-004**: Browser developer-tools inspection of any page running the widget shows zero token-shaped values in cookies, localStorage, sessionStorage, or IndexedDB at any point during or after the session.
- **SC-005**: A credential captured by a network observer and replayed after its lifetime window has elapsed is rejected by 100% of downstream consumers.
- **SC-006**: Tokens issued for tenant A cannot, under any tested condition, be used to access tenant B's data — verified by the cross-tenant smoke test (Phase 7 in the work plan).
- **SC-007**: A widget belonging to a suspended or erased tenant produces zero successful credential issuances (verified by a tenant-lifecycle test that toggles status mid-flow).
- **SC-008**: An operator inspecting the structured logs from a 24-hour window can identify the volume of token refusals broken down by reason bucket (unknown-widget, origin-not-allowlisted, widget-disabled, tenant-not-active, rate-limited-per-ip, rate-limited-per-widget), enabling detection of an enumeration probe by comparing against baseline volumes.
- **SC-009**: Inspection of any log line or trace span emitted by this feature shows zero unhashed widget identifiers, zero unhashed visitor IP addresses, zero raw tokens, and zero JWT signing secrets — across a sample of 100 randomly selected entries (verified by an automated redaction test, satisfying Constitution Principle V).

## Assumptions

- **Widget provisioning is out of scope here.** A tenant admin (or platform tenant manager) is responsible for creating the widget configuration row, setting its allowed-origins list, and enabling it before any visitor exchange occurs. That provisioning UI is a separate piece of work (Phase 4 in Amer's plan).
- **Origin matching ignores path/query/fragment.** This matches industry practice (the browser `Origin` header itself is scheme + host + port).
- **The cryptographic signing material is configured at platform start-up.** A production-grade secret store integration (rotation, audit) is out of scope here; an environment-variable-backed secret is acceptable for this phase and will be swapped for a vault-backed secret later (separate work, Ayoub's slice).
- **Token lifetime defaults to 15 minutes.** This is the industry-standard short-lived web session window. It is configurable at the platform level but not per-tenant in this phase.
- **No token revocation list — conscious deferral.** Tokens are stateless and the sole mitigation for a leaked or post-revocation token is its short lifetime (FR-009). This trade-off is to be re-evaluated when either (a) a tenant explicitly requests immediate revocation, or (b) an incident demonstrates the 15-minute window is too long. Until one of those triggers fires, no revocation surface is built.
- **Visitors are anonymous.** No human authentication is performed for the widget session beyond proving the request came from an allowlisted origin.
- **The chat backend already accepts a bearer credential** and will be the primary consumer of the issued token. That consumer is owned by another team and is contractually defined elsewhere.
- **Rate limiting on the token endpoint is owned by this feature** at the per-IP and per-widget level (FR-015 through FR-019). The per-tenant rate limiter operated by the tenancy platform applies on top.
- **The widget loader script is delivered from the platform**, not from each tenant's CDN, so the loader is uniform across all tenants.

## Out of Scope (mirrored from input)

- Vault integration for the signing key — environment variable is acceptable for this phase.
- The chat UI rendering and message handling (separate piece of work).
- The admin UI for managing the allowed-origins list (separate piece of work).
- Token refresh on expiry — for this phase, an expired token results in the widget being reloaded and a fresh exchange.
