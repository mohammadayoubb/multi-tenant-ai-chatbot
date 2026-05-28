# Phase 1 Data Model: Demo Polish

**Feature**: 008-demo-polish
**Date**: 2026-05-28

This feature introduces **no database tables, no schemas, no migrations, and no in-memory data structures** in application code. There is nothing for ORM models to represent.

What this feature does introduce — and what therefore deserves an "entity"-shaped treatment so reviewers and downstream `/speckit-tasks` have a single source of truth — is a small set of **documentation and CI artifacts**. Each is described below with its required fields, validation rules, and lifecycle.

---

## E1. README Embed Section

**Represents**: A documentation block in `README.md` that teaches a non-contributor how to load the widget on a third-party page.

**Required fields (sections of the block)**:
- A level-2 heading: `## Embed the widget`.
- A one-line preface that names the allowlist requirement.
- A fenced HTML code block containing exactly one `<script>` tag with the attributes `src`, `data-widget-id`, and `data-backend-url`.
- A short paragraph (two sentences) explaining where `YOUR_WIDGET_ID` comes from and that the loading page's origin must be allowlisted.

**Validation rules**:
- The `<script>` tag MUST include all three of `src`, `data-widget-id`, `data-backend-url`. Missing any attribute fails FR-001.
- Placeholder values MUST be obviously non-real (ALL-CAPS or marker domains like `YOUR-CONCIERGE-HOST`). No real customer domain, no real widget ID, no real backend URL.
- The block MUST be reachable from the README's table of contents / surrounding flow (i.e., not orphaned at the bottom of the file with no context).

**Lifecycle**: Created once in this feature; subsequent edits happen only when widget attributes change (a constitutional moment, would touch `CONTRACT.md`).

---

## E2. RUNBOOK Demo Flow

**Represents**: The numbered nine-step Demo Flow plus the tenth "Run smoke test" line in `RUNBOOK.md`.

**Required fields (per step)**:
- An ordinal (1–9 for demo steps; the smoke test is a separate sub-section).
- A one-line goal (what the presenter is demonstrating in this step).
- A concrete shell command or UI action, copy-pasteable as-is.
- Where applicable, the observable success signal (e.g., "agent declines; admin audit-log shows rejection").

**Validation rules**:
- Every command MUST run successfully on a clean clone without undocumented manual edits (FR-003).
- Steps 1–9 cover, in order: start stack, seed tenants, open host page for Tenant A, ask Tenant A question, attempt Tenant B extraction, observe refusal, capture lead, escalate, show CI gates.
- The smoke test invocation MUST be a single command line and MUST be `pytest tests/smoke/` (per the user's explicit request).

**Lifecycle**: Authored in this feature. Re-validated on every demo run; any drift discovered in a future run is fixed in a follow-up doc PR, not silently tolerated.

---

## E3. Lean Image Audit (script + Makefile target + CI job)

**Represents**: The end-to-end mechanism that asserts `modelserver` and `guardrails` images contain neither `torch` nor `transformers`.

**Required fields**:
- `scripts/check_lean_images.sh`: a bash script that takes no arguments by default and audits the two named images. Optionally accepts `--image <name>` (repeatable) to audit a different set, used in tests.
- `Makefile`: a single target `lean-image-audit` whose recipe invokes the script. The Makefile MAY contain other targets in the future, but this feature only adds this one.
- `.github/workflows/ci.yml`: a new job `lean-image-audit` that runs `docker compose build modelserver guardrails`, then `make lean-image-audit`.

**Validation rules**:
- The script MUST exit 0 when both images are clean and exit 1 otherwise (per `lean-image-audit-cli.md` contract).
- The script's failure output MUST identify both the image and the forbidden package name (FR-007).
- The CI job MUST be wired so that a failure blocks merge (FR-008). This is achieved by the job being a required check in branch protection, but that configuration is repo-admin scope and is not part of this PR.
- The audit MUST NOT modify the images it inspects (read-only inspection via `docker run --rm`).

**Lifecycle**: Created in this feature. Survives untouched unless the constitution changes which packages are forbidden, in which case the regex inside the script changes in the same PR that amends the constitution.

---

## E4. Compose Health Topology

**Represents**: The healthchecks and `depends_on` edges declared in `docker-compose.yml` that together guarantee no service starts serving traffic before its upstreams are ready.

**Required fields**:
- A `healthcheck:` block on every service that another service health-gates against: `db`, `redis`, `vault`, `modelserver`, `guardrails`, `api`.
- Every `depends_on` entry that requires the upstream to be **ready** MUST use the long-form `condition: service_healthy`.

**Validation rules**:
- Three consecutive `docker compose down -v && docker compose up --build --wait` cycles MUST all reach a healthy state without manual retry (FR-011, SC-003).
- The single race identified in R5 (`admin` short-form `depends_on: - api`) MUST be changed to long-form with `condition: service_healthy` before merge.
- No speculative healthchecks are added to services that nothing depends on (Principle VII).

**Lifecycle**: Edited in this feature only if R5's audit finds a real fix needed. No further changes expected post-demo.

---

## E5. Demo Screenshot Set (out-of-repo)

**Represents**: Three image files captured from a running demo: admin audit-log rejection, widget mid-chat, CI page with all gates green.

**Required fields**:
- One image per scenario (PNG or equivalent), at a resolution legible during a presentation.
- A pointer-only reference in the team writeup (not in this repo).

**Validation rules**:
- Images MUST contain only seeded/demo data — no real tenant data, no live secrets, no tokens visible in screenshots (constitutional redaction posture, even for images).
- Images MUST NOT be staged or committed to the repository (FR-012). The runbook's screenshot subsection explicitly notes "do not `git add` these."

**Lifecycle**: Captured immediately before the demo; archived with the writeup; lifecycle ends with the demo. Not regenerated as part of any CI run.

---

## Relationships

```text
README Embed Section (E1)  ──documents──>  Widget Loader (existing, untouched)
RUNBOOK Demo Flow (E2)     ──invokes────>  Docker Compose stack (E4)
                            ──invokes────>  pytest tests/smoke/ (existing)
Lean Image Audit (E3)      ──inspects───>  modelserver image, guardrails image
                            ──enforced by─>  Constitution Principle V
Compose Health Topology    ──supports────>  RUNBOOK Demo Flow (E2)
(E4)                        ──supports────>  CI smoke-e2e job (existing)
Demo Screenshot Set (E5)   ──captured-from->  Running demo instance (out of repo)
```

No new tenant-bearing data is introduced anywhere in the model. Constitution Principle I is therefore trivially satisfied (no new tables, no new queries).
