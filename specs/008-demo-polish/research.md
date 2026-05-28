# Phase 0 Research: Demo Polish

**Feature**: 008-demo-polish
**Date**: 2026-05-28
**Status**: Resolved — no NEEDS CLARIFICATION items remain

This document resolves every open question the plan depends on. Each section follows the Decision / Rationale / Alternatives format.

---

## R1. How should the lean-image-audit invoke `pip list` inside the built images?

**Decision**: Use `docker run --rm --entrypoint pip <image> list --format=freeze`, then grep the output for `^(torch|transformers)([=\s]|$)` (case-insensitive). Exit non-zero on any match, naming the image and the offending package.

**Rationale**:
- `docker run --rm --entrypoint pip` reuses the already-built image and overrides the long-running `uvicorn` CMD with a one-shot `pip` invocation. No new image layer, no separate build step.
- `--format=freeze` gives one package per line in a stable, regex-friendly shape (`name==version`), avoiding the column-aligned default format that can shift with `pip` versions.
- The image tag will be the same tag Compose uses (e.g., `multi-tenant-ai-chatbot-modelserver` and `-guardrails`), so the audit runs immediately after `docker compose build` with no extra `docker build` invocation.

**Alternatives considered**:
- **`docker compose run --rm --entrypoint pip <service> list`**: equivalent behavior but requires `.env` and the full Compose network to be configured. Slower, more moving parts, no benefit.
- **`docker image inspect` + parsing the manifest**: gives metadata, not installed packages. Cannot detect packages that were installed but not registered as a layer label. Rejected.
- **A Python-import-based check (`docker run ... python -c "import torch"`)**: only catches `torch` if it can be imported at runtime, which depends on the platform binary wheel landing. `pip list` is the authoritative ground truth and is faster.
- **`syft` or another SBOM tool**: heavier dependency for a check that needs to be two `grep` lines. Rejected per Constitution Principle VII.

---

## R2. Should the lean-check be a Makefile target, a shell script, both, or only a CI step?

**Decision**: Both — a shell script `scripts/check_lean_images.sh` that does the work, plus a Makefile target `lean-image-audit` that invokes it. CI calls the Makefile target so developers and CI run the same command.

**Rationale**:
- The user's request explicitly offered "CI check (or a Makefile target Amer adds)." The script + Makefile target answers both: contributors get `make lean-image-audit` locally; CI gets a one-line `make lean-image-audit` step.
- Keeping the logic in a shell script (not inline in YAML) means developers can run it, debug it, and add to it without editing the workflow file.
- A `Makefile` does not previously exist in this repo (`Makefile` is absent from the root `ls`). Introducing one with a single target is justified by giving CI and contributors a stable entry point; future Amer-owned automation can append targets without touching CI YAML.

**Alternatives considered**:
- **Inline `run:` block in `ci.yml`**: smaller PR but no local equivalent for contributors. Rejected.
- **`scripts/check_lean_images.py` (Python)**: would need to shell out to `docker` anyway. Shell is simpler and matches the existing pattern of other shell-style operational checks. Python is reserved for logic with non-trivial branching.
- **Makefile only, no script**: Makefile recipes are awkward for multi-line shell logic on Windows and have whitespace pitfalls (tab vs. spaces). The script keeps the logic portable and readable.

---

## R3. Where in `ci.yml` does the lean-image-audit job belong?

**Decision**: A new job named `lean-image-audit`, placed **after** `lint-test-build` (so it can rely on the build succeeding) and **before** the five eval jobs and `smoke-e2e`. It runs on every push and pull_request (no `if:` gate), because the constitutional rule it enforces applies to every commit, not just PRs to main.

**Rationale**:
- `lint-test-build` already runs `docker compose build`, which materializes the `modelserver` and `guardrails` images. The audit job can re-run `docker compose build` cheaply (cached layers) and then introspect — total marginal cost ~30s.
- Placing it before the heavy eval jobs means a constitutional violation short-circuits CI early, saving runner minutes.
- The job is needs: `[lint-test-build]` only. Eval jobs already `needs: lint-test-build` independently; they do not need to `needs: lean-image-audit` because a failure here will not invalidate the eval results — it will simply fail the PR via its own status check.

**Alternatives considered**:
- **Run inside `lint-test-build`**: couples two distinct concerns (general build/test vs. constitutional image audit) under one status check, which makes the PR page less scannable. Rejected per the design rationale already documented in `ci.yml` header comment for the five separate eval jobs.
- **Run only on pull_request**: would let a direct main-branch push (theoretically blocked by branch protection, but defensively we assume it) introduce `torch`. Cheap to run, so run it always.

---

## R4. Runbook drift inventory — which existing steps no longer match reality?

**Decision**: The current `RUNBOOK.md` Demo Flow (lines 35–45) lists nine bare labels with no commands. Rather than "fix" individual drifted steps, replace the bullet list with nine numbered steps, each with the actual shell command that works on a clean clone in 2026-05-28. The replacement reads as follows (final wording lives in `RUNBOOK.md` itself, this is the inventory):

1. **Start the stack**: `docker compose up --build --wait` (replaces "Start stack" — adds `--wait` so the command exits only when all healthchecks pass; this is the same flag used in CI).
2. **Seed two tenants**: `python scripts/seed_tenants.py` (replaces "Seed two tenants" — this script already exists per `ls scripts/`).
3. **Open the host page for Tenant A**: navigate to `http://localhost:5173/host-test.html` (replaces "Load widget for Tenant A" — the host-test page exists at `frontend/widget/dist/host-test.html` and is documented in spec 003).
4. **Ask a Tenant A-specific question**: type a question grounded in Tenant A's seeded CMS content (replaces "Ask a tenant-specific question" — unchanged, but explicit).
5. **Attempt to extract Tenant B content**: ask a question whose answer would require Tenant B data (replaces "Try to extract Tenant B content").
6. **Observe the refusal**: agent declines / responds with grounded refusal; the audit log on the admin page shows the rejection (replaces "Show refusal" — adds the audit-log pointer that the demo screenshot depends on).
7. **Capture a lead**: trigger the `capture_lead` flow by giving the agent a contact email (replaces "Capture a lead").
8. **Escalate to human**: ask the agent to escalate; observe the conversation marked for follow-up (replaces "Escalate to human").
9. **Show CI gates**: open the GitHub Actions page for the latest commit on `main` and show all gate status checks green (replaces "Show CI gates" — adds the explicit "all gates green" assertion that matches the screenshot).

Then a tenth, non-demo bullet adds the smoke test invocation:

- **Run the end-to-end smoke test against a running stack**: `pytest tests/smoke/` (or `python scripts/smoke_check.py -v` for the parametrized wrapper). This is the line FR-005 requires.

**Rationale**:
- The smoke runner already exists in two forms: the pytest suite at `tests/smoke/` (used by CI's `smoke-e2e` job indirectly via the wrapper) and the wrapper `scripts/smoke_check.py`. Either works; the runbook documents both with a note that `pytest tests/smoke/` is the canonical local invocation per the user's request.
- `docker compose up --build --wait` matches CI's `docker compose up -d --wait` and is the safest single command — it builds, starts, and blocks until healthchecks pass.
- The host-test page exists in the widget `dist/` already; documenting its URL avoids the demo team writing an ad-hoc HTML harness.

**Alternatives considered**:
- **Preserve the original bare-label list and add commands as inline comments**: less readable and harder to follow during a live demo. Rejected.
- **Document only `scripts/smoke_check.py`, not `pytest tests/smoke/`**: the user explicitly asked for `pytest tests/smoke/`. Document the pytest invocation as primary, mention the wrapper as the CI-equivalent shape.

---

## R5. Compose race inventory — does any `depends_on` chain race on cold start?

**Decision**: Audit the current `docker-compose.yml` for two issues: (a) any `depends_on` short-form (just a list) where the dependent service needs the upstream to be **healthy**, not merely started; (b) any service that calls another service at startup but does not declare a `depends_on` at all. Inventory:

| Service | Current `depends_on` | Verdict | Action |
|---------|----------------------|---------|--------|
| `api` | `db: service_healthy`, `redis: service_healthy`, `vault: service_healthy`, `modelserver: service_healthy`, `guardrails: service_healthy` | ✅ Correct. Five health-gated dependencies. | None. |
| `admin` | `- api` (short-form) | ⚠ Short-form means "start after api started" — does not wait for `api` to be healthy. Streamlit will attempt to call the API on first user action; if a user opens the admin tab during the few seconds between `api` starting and the openapi route responding, they get a transient error. | **Fix**: change to `api: condition: service_healthy`. |
| `modelserver` | (none) | ✅ Modelserver has no startup dependencies on other services in this stack (it loads its ONNX artifact from local disk). | None. |
| `guardrails` | (none) | ✅ Same — guardrails sidecar boots independently. | None. |
| `widget` | (none) | ✅ Static asset server; no upstream dependencies. | None. |
| `db`, `redis`, `minio`, `vault` | (none) | ✅ Leaf infrastructure. | None. |

Healthchecks: `api`, `modelserver`, `guardrails`, `db`, `redis`, `vault` all have healthchecks. `admin`, `widget`, `minio` do not — and do not need to, because nothing health-gates against them.

**Rationale**:
- The single race is `admin → api` via short-form `depends_on`. Fixing to `condition: service_healthy` makes `admin` wait for the api's openapi probe to succeed. Cost: a few extra seconds of `admin` boot. Benefit: no transient-error demo footgun.
- No other change is justified by an actual race. Adding `minio` or `widget` healthchecks for symmetry would be speculative scope (Principle VII).

**Alternatives considered**:
- **Add healthchecks to `admin`, `widget`, `minio` "for completeness"**: nothing depends on them being healthy, so the healthchecks would be cosmetic. Rejected.
- **Add explicit `modelserver → db` / `guardrails → db` edges**: neither service queries the database at startup; doing so would lengthen cold-start and add a phantom dependency. Rejected unless a real boot-time DB call is discovered.

---

## R6. Where do the demo screenshots live, and how are they kept out of git?

**Decision**: Screenshots are captured by the presenter (Amer) into a local `demo-assets/` directory and stored outside the repository — typically in the team's shared drive folder used for the writeup, or in the presentation file itself. They are referenced from the writeup, not from the repo. The runbook describes how to capture each one but does not commit any image files. `.gitignore` already excludes generic image patterns under most repos, but for safety the runbook explicitly states "do not `git add` any file under `demo-assets/`."

**Rationale**:
- The user's instruction was explicit: "Capture demo assets (out-of-repo, not committed)." This is honored by not putting the images in the repo at all.
- No `.gitignore` change is required because nothing under the documented capture path gets staged.

**Alternatives considered**:
- **Commit screenshots under `docs/demo/` and rely on Git LFS**: introduces LFS as a project dependency for a one-time demo asset. Rejected.
- **Generate screenshots automatically via a Playwright script committed to the repo**: out-of-scope (FR-013: no new product features) and would itself require a CI runner with a browser. Rejected.

---

## R7. README "Embed the widget" snippet — what exact attributes and what placeholder shape?

**Decision**: The README snippet mirrors the working host-test page already in the repo (`frontend/widget/dist/host-test.html`), but uses explicit placeholder values and adds a one-line preface:

```html
<!-- Drop this on a page served from an origin in your tenant's allowlist. -->
<script
  src="https://YOUR-CONCIERGE-HOST/widget.js"
  data-widget-id="YOUR_WIDGET_ID"
  data-backend-url="https://YOUR-CONCIERGE-HOST"
></script>
```

A second paragraph below the snippet explains, in two sentences: (a) where to get `YOUR_WIDGET_ID` (from the admin UI per the existing widget config flow), and (b) that the loading page's origin must be on the tenant's allowlist or the widget session call will be refused server-side.

**Rationale**:
- Mirrors the verified-working host-test snippet — no risk of documenting an attribute name that the loader does not actually read.
- Placeholder values use ALL-CAPS to make them obviously substitutable. No real domains, no real widget IDs.
- The two-sentence allowlist note is the minimum a reader needs to avoid the demo-killing failure mode (snippet on a non-allowlisted origin → silent failure). It does not document the auth flow in detail — that lives in `SECURITY.md` and spec 001.

**Alternatives considered**:
- **Embed the script tag with a `data-debug` attribute or local-dev URLs**: confuses the "tenant copies this to their site" use case. Keep the snippet production-shaped.
- **Document `defer` or `async` semantics inline**: the host-test page's NOTE comment (do not add `async`) is loader-internal detail; the README is for tenants, not loader authors. Skip.

---

## R8. Is there a risk that the lean-image-audit produces a false positive?

**Decision**: No. The audit matches against `^(torch|transformers)([=\s]|$)` with case-insensitivity. This will not match unrelated names such as `transformers-extensions-mock` (no such package exists in our dep graph) or `torchvision` (would not be present without `torch`, but if it were, it would be caught by the `torch` line of the failure message — which is the correct outcome since `torchvision` implies `torch`).

**Rationale**:
- We control the dependency closure via `pyproject.toml`. The audit is a constitutional gate, not a generic SBOM scanner; the regex is purposely narrow to the two names called out in the constitution.
- If a future legitimate dependency starts with `torch` or `transformers` and is non-DL (extremely unlikely), the audit can be updated in the same PR that introduces it — and that change would itself be a constitutional moment worth reviewing.

**Alternatives considered**:
- **Match the exact name `^(torch|transformers)==`**: equally safe, slightly less defensive against `pip list` output format drift. The chosen regex tolerates both freeze and column output.

---

## Summary of Findings

| Question | Outcome |
|----------|---------|
| R1. Lean-check mechanism | `docker run --rm --entrypoint pip <image> list --format=freeze` + grep |
| R2. Makefile vs. script vs. CI | All three: script does work, Makefile invokes script, CI invokes Makefile |
| R3. CI placement | New `lean-image-audit` job, needs `lint-test-build`, runs on all events |
| R4. Runbook drift | Replace nine bare labels with nine command-bearing steps; add pytest smoke line |
| R5. Compose race | One real race: `admin → api` is short-form; fix to `condition: service_healthy` |
| R6. Screenshots | Out-of-repo, captured by presenter into team writeup, no .gitignore changes |
| R7. README snippet | Production-shaped snippet with ALL-CAPS placeholders + two-line allowlist note |
| R8. Audit false-positive risk | None — narrow regex against narrow dependency closure |

No NEEDS CLARIFICATION items remain. Phase 1 can proceed.
