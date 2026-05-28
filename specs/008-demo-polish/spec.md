# Feature Specification: Demo Polish

**Feature Branch**: `008-demo-polish`
**Created**: 2026-05-28
**Status**: Draft
**Input**: User description: "Polish for demo. Files Amer touches: README.md (Embed the widget section), RUNBOOK.md (clean-clone demo flow + smoke test command), Dockerfile / Makefile (CI check that modelserver and guardrails images contain no torch/transformers), docker-compose.yml (verify healthchecks for api/modelserver/guardrails, fix racey depends_on). Capture demo screenshots out-of-repo. No new features. No incidental refactors."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Embed instructions a new integrator can follow (Priority: P1)

A prospective tenant or reviewer opens the repo's `README.md` and finds a clearly-labeled "Embed the widget" section showing the exact HTML snippet — including the `data-widget-id` and `data-backend-url` attributes — that they can paste into their own site to load the chat widget.

**Why this priority**: The widget is the user-visible product. If reviewers cannot find the embed snippet in the README, the demo loses the "drop this on your site" moment. This is the single highest-leverage README change for the demo.

**Independent Test**: A reader who has never seen this project clones the repo, opens `README.md`, copies the snippet under "Embed the widget" into a blank HTML page served from an allowlisted origin, loads the page in a browser, and the widget mounts and connects to the configured backend.

**Acceptance Scenarios**:

1. **Given** a clean clone of the repository, **When** a reader opens `README.md`, **Then** they find a section titled "Embed the widget" containing a runnable HTML snippet with both `data-widget-id` and `data-backend-url` attributes shown explicitly.
2. **Given** the snippet from `README.md`, **When** a reader pastes it into an HTML page on an allowlisted host and opens that page, **Then** the widget loads, fetches a session token, and a chat conversation succeeds end-to-end.

---

### User Story 2 - The runbook reflects what actually happens on a clean clone (Priority: P1)

A reviewer follows `RUNBOOK.md` step by step on a clean clone and reaches a working local demo: services start, the admin UI is reachable, the widget loads on a host page, and the smoke test can be executed from a single documented command.

**Why this priority**: The runbook is the demo script. Any drift between the documented steps and the current code means the demo will fail live. The smoke-test command is what the team will run on-camera to prove the system is healthy.

**Independent Test**: From a fresh `git clone`, follow `RUNBOOK.md` from the first command. Every command runs without manual edits or fix-ups, and the "Run smoke test" command exits zero against the running local stack.

**Acceptance Scenarios**:

1. **Given** a clean clone with no prior local state, **When** a reviewer follows the Demo Flow in `RUNBOOK.md` top-to-bottom, **Then** every documented command succeeds without needing undocumented edits to files, env vars, or service config.
2. **Given** the local stack is running per the runbook, **When** the reviewer runs the documented "Run smoke test" command, **Then** the smoke test exits successfully and the runbook explains what passing means.
3. **Given** a step in the current runbook no longer matches reality (wrong path, wrong command, removed env var, renamed service), **When** the runbook is updated, **Then** the corrected step works on a clean clone.

---

### User Story 3 - Serving images are provably free of torch and transformers (Priority: P1)

A reviewer (or CI) can run a single command to assert that the `modelserver` and `guardrails` container images do not contain `torch` or `transformers`. The assertion fails loudly with a clear message if either package is present.

**Why this priority**: Constitution Principle V forbids `torch`/`transformers` in serving containers. The demo claim "we keep serving containers lean" must be machine-verifiable, not just visually inspected. This is a security and integrity gate, not a nice-to-have.

**Independent Test**: With local images built, run the documented check command (Makefile target or CI step). It exits zero when both images are clean. Temporarily install `torch` in either image and re-run; the check exits non-zero and the failure message names the offending package and image.

**Acceptance Scenarios**:

1. **Given** the `modelserver` and `guardrails` images built from the current Dockerfiles, **When** the check runs `pip list` inside each image, **Then** the check exits zero and reports both images as clean.
2. **Given** an image that contains `torch` or `transformers` (for any reason), **When** the check runs, **Then** the check exits non-zero and the output identifies which image and which forbidden package was found.
3. **Given** the check is wired into CI, **When** a PR introduces a Dockerfile change that pulls in `torch` or `transformers`, **Then** CI blocks the merge.

---

### User Story 4 - The local stack starts cleanly, every time (Priority: P2)

When a reviewer runs the single documented compose-up command, `api`, `modelserver`, and `guardrails` come up healthy with no race-condition retries, no transient "connection refused" loops, and no dependent service starting before its upstream is ready.

**Why this priority**: A flaky startup turns a 60-second demo into a 5-minute apology. Healthchecks + correctly-ordered `depends_on` (with `condition: service_healthy`) are the difference between a clean demo and a coin-flip.

**Independent Test**: From a stopped state, run the documented compose-up command three times in a row (down + up each time). All three runs reach a healthy state for `api`, `modelserver`, and `guardrails` without manual intervention, and the first successful health probe on `api` does not predate `modelserver` or `guardrails` being healthy.

**Acceptance Scenarios**:

1. **Given** `docker-compose.yml`, **When** a reviewer inspects it, **Then** `api`, `modelserver`, and `guardrails` each declare a healthcheck appropriate to that service.
2. **Given** the current `depends_on` chains, **When** the stack starts, **Then** services that depend on `modelserver` or `guardrails` wait for those to be healthy (not merely started) before they begin accepting traffic.
3. **Given** the stack is started three consecutive times from a clean state, **When** each run is observed, **Then** all three runs reach a healthy state without manual restart, retry, or undocumented intervention.

---

### User Story 5 - Demo screenshots exist and are accessible to the presenter (Priority: P3)

The presenter has three screenshots ready to show during the demo: (a) the admin tenant page with an audit-log entry showing a cross-tenant attempt being rejected; (b) the widget mid-chat on a host page; (c) the CI page with all gates green.

**Why this priority**: These are demo aids, not product. They make the story tellable when live capture would be slow or risky, but they are not on the merge path. Lower priority because they live outside the repo and have no code impact.

**Independent Test**: The presenter can produce each of the three screenshots on demand from local state (admin page, host page with widget, CI page on the latest green build). The screenshots are stored somewhere the presenter can open them in under five seconds during the demo.

**Acceptance Scenarios**:

1. **Given** the local stack is running with seeded tenant data, **When** the presenter triggers a cross-tenant access attempt and opens the admin audit-log view, **Then** a screenshot can be captured showing the rejection entry with tenant and action visible.
2. **Given** the widget is loaded on a host page, **When** the presenter has exchanged at least two turns with the agent, **Then** a screenshot of the mid-chat state can be captured.
3. **Given** the latest successful CI run, **When** the presenter opens the CI page, **Then** a screenshot of all gates green can be captured.
4. **Given** the three screenshots exist, **When** the demo runs, **Then** none of them are committed to the repo.

---

### Edge Cases

- A reader copies the README snippet but uses a `data-backend-url` that points to a non-allowlisted origin: the widget must fail to obtain a session (existing behavior). The snippet should make the allowlist requirement obvious enough to avoid this misuse during a demo.
- A runbook step depends on optional or developer-only tooling (e.g., a global `make`, a specific Python version, GPU drivers). On a clean clone without those, the step must either be guarded with a clear prerequisite or replaced with a portable equivalent.
- The torch/transformers check runs against an image that does not exist locally yet: the check should build or pull as documented, or fail with a clear "image not built — run X first" message rather than a confusing pip error.
- A healthcheck command exists on a service but never returns healthy because the probe is wrong (wrong port, wrong path): the check must reflect the service's actual ready signal, not just "process is running."
- A `depends_on` entry uses the short form (start order only) where `condition: service_healthy` is needed: starting order without health-gating still races.
- A screenshot reveals tenant data, secrets, or tokens that should not be visible: the capture process must use seeded/demo data only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `README.md` MUST contain a section titled "Embed the widget" that shows the complete HTML snippet required to load the widget on a third-party page, including both `data-widget-id` and `data-backend-url` attributes with clearly-marked placeholder values.
- **FR-002**: The README embed snippet MUST be copy-pasteable: it must not assume any prior README context, and a reader who pastes only the snippet onto a configured host page must get a working widget.
- **FR-003**: `RUNBOOK.md` MUST describe a Demo Flow that, when followed step-by-step on a clean clone, results in a healthy local stack and a successful smoke test without undocumented manual fix-ups.
- **FR-004**: Any step in the existing runbook that no longer matches reality (wrong command, wrong path, removed env var, renamed service, removed flag) MUST be corrected.
- **FR-005**: `RUNBOOK.md` MUST contain a single, copy-pasteable "Run smoke test" command line and state what a passing result looks like.
- **FR-006**: A documented mechanism (Makefile target, script, or CI job) MUST exist that runs `pip list` inside the built `modelserver` and `guardrails` images and exits non-zero if `torch` or `transformers` is present in either.
- **FR-007**: The torch/transformers check MUST identify, in its failure output, which image and which forbidden package triggered the failure.
- **FR-008**: The torch/transformers check MUST be wired into CI so that a PR introducing either package into a serving image blocks merge.
- **FR-009**: `docker-compose.yml` MUST have a healthcheck for each of `api`, `modelserver`, and `guardrails` that reflects the service's actual readiness signal (not merely process start). If a verification of the current file shows all three already present and correct (research R5 confirms this), no new healthcheck blocks need be added.
- **FR-010**: Every `depends_on` relationship in `docker-compose.yml` where the dependent service requires its upstream to be ready (not just started) MUST use `condition: service_healthy`.
- **FR-011**: The local stack MUST reach a healthy state for `api`, `modelserver`, and `guardrails` on three consecutive clean starts without manual intervention.
- **FR-012**: The three demo screenshots (admin audit-log rejection, widget mid-chat, CI gates green) MUST be capturable on demand from the current system; they MUST NOT be committed to the repository.
- **FR-013**: No new product features, routes, schemas, services, or migrations may be added under this spec.
- **FR-014**: Refactors not strictly required to make the README, runbook, Docker check, or compose healthchecks correct are out of scope.
- **FR-015**: Protected files modified by this PR MUST be listed in the PR description with a one-line justification each, and the set of protected files changed MUST be a subset of `{docker-compose.yml, .github/workflows/ci.yml}`. Changes affecting service credentials or guardrails are out of scope here.

### Key Entities

- **README Embed Section**: A documentation block in `README.md` whose responsibility is to teach a non-contributor how to load the widget on their own page. Inputs: the widget script URL, a widget ID, a backend URL. Output: a runnable HTML snippet.
- **Demo Flow (Runbook)**: An ordered sequence of shell commands and observable checkpoints in `RUNBOOK.md` that takes a reviewer from `git clone` to a passing smoke test. Properties: each step is deterministic, each step's success criterion is stated.
- **Smoke Test Invocation**: The single command line documented in the runbook that exercises the end-to-end happy path against the running local stack. Properties: exits zero on success, produces an artifact or log line a presenter can point to.
- **Serving Image Lean-Check**: An automated assertion that introspects the `modelserver` and `guardrails` images for forbidden Python packages (`torch`, `transformers`). Properties: deterministic, runs in CI, produces an actionable failure message.
- **Compose Health Topology**: The set of healthchecks and `depends_on … condition: service_healthy` edges in `docker-compose.yml`. Properties: each serving service has a real readiness probe; no dependent service starts traffic before its upstream is healthy.
- **Demo Screenshot Set**: Three out-of-repo image files captured from a running demo instance. Properties: contain only seeded/demo data, are not committed, are accessible to the presenter during the demo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reader who has never seen this project can copy the snippet from the README "Embed the widget" section into a blank HTML page on an allowlisted host and get a working widget without reading any other repo file. Target: at least one independent reviewer (other than the author) completes this end-to-end before merge.
- **SC-002**: A reviewer following `RUNBOOK.md` top-to-bottom on a clean clone reaches a passing smoke test in under 15 minutes of wall-clock time, with zero undocumented manual edits.
- **SC-003**: On three consecutive `down → up` cycles of the local compose stack from a clean state, `api`, `modelserver`, and `guardrails` reach the `healthy` state in 100% of runs with no manual retry.
- **SC-004**: The serving-image lean-check runs in CI on every PR and blocks merge in 100% of cases where `torch` or `transformers` is present in `modelserver` or `guardrails`. (Post-merge observation, not a merge-blocking criterion: zero false positives across the most recent ten green builds.)
- **SC-005**: The presenter can produce each of the three required demo screenshots in under five minutes total from the running local stack.
- **SC-006**: No file outside the documented scope (README.md, RUNBOOK.md, Dockerfile / Makefile / CI wiring for the lean-check, docker-compose.yml) is modified under this spec.

## Assumptions

- The widget script is already served at a stable path that the README snippet can reference; if not, the snippet uses a clearly-marked placeholder and the runbook explains how to derive the real value locally.
- The `modelserver` and `guardrails` Dockerfiles already exist and are buildable; this work only adds the post-build introspection, not the image definitions.
- CI already exists (per spec 006-ci-eval-gates) and has a place where a new job can be wired in; this work does not stand up new CI infrastructure.
- The smoke test itself already exists (per spec 007-cross-tenant-smoke-e2e); this work only documents its invocation in the runbook, it does not change the smoke test.
- Healthcheck endpoints needed for the compose healthchecks already exist or can be expressed with the service's existing entry points (e.g., a simple HTTP probe against an existing route); adding new product endpoints is out of scope.
- Demo screenshots are produced and stored outside the repository (local disk, shared drive, presentation deck) per the user's explicit instruction.
- "Clean clone" means a fresh `git clone` plus whatever the runbook documents as prerequisites (Docker, Python, etc.); it does not mean "zero tooling on the machine."
