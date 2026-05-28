# Quickstart: Demo Polish

**Feature**: 008-demo-polish
**Audience**: The person running the demo, and the contributor who will land this PR.

This is the short version of how to verify each piece of the demo polish locally and how to capture the three demo screenshots.

---

## 1. Verify the README embed snippet works

```powershell
# From a fresh clone:
docker compose up --build --wait

# Copy the snippet under "Embed the widget" in README.md into a blank HTML page
# served from an allowlisted origin. For local testing, the seeded host page is
# already served at:
#   http://localhost:5173/host-test.html
# Open it. The widget should mount, fetch a token, and let you chat.
```

Success looks like: widget pinned bottom-right, no console errors, a chat reply comes back.

---

## 2. Walk the runbook from scratch

```powershell
git clone <repo>
cd multi-tenant-ai-chatbot
# Follow RUNBOOK.md from step 1 through step 9, then run the smoke test:
pytest tests/smoke/
```

Success looks like: every step's command runs without manual fix-ups; `pytest tests/smoke/` exits 0.

Time budget per SC-002: under 15 minutes wall-clock on a developer laptop.

---

## 3. Run the lean-image audit locally

```powershell
docker compose build modelserver guardrails
make lean-image-audit
```

Success looks like:

```text
lean-image-audit: clean (2 images, 2 regexes)
```

To verify the failure path (do not commit this Dockerfile change):

```powershell
# Temporarily add `RUN pip install torch` to the modelserver stage of Dockerfile
docker compose build modelserver
make lean-image-audit
# Expect exit code 1 and stderr naming the image and the package.
# Revert the Dockerfile change.
```

---

## 4. Verify the compose stack starts cleanly three times in a row

```powershell
1..3 | ForEach-Object {
  Write-Host "=== Run $_ ==="
  docker compose down -v
  docker compose up --build --wait
  docker compose ps
}
docker compose down -v
```

Success looks like: every run reports `api`, `modelserver`, `guardrails` in `healthy` state under `docker compose ps`. SC-003 requires 3/3.

---

## 5. Capture the three demo screenshots

These are captured by the presenter into local disk or directly into the writeup deck. **They are not committed to the repo.**

### Screenshot 1 — Admin tenant page audit log showing a cross-tenant rejection

1. Start the stack and seed two tenants (runbook steps 1–2).
2. Open the admin UI at `http://localhost:8501`.
3. From a Tenant A widget session, ask a question that requires Tenant B data.
4. Observe the agent refusal (runbook step 6).
5. In the admin UI, navigate to the tenant audit-log view and capture the row showing the cross-tenant attempt was rejected.

### Screenshot 2 — Embedded widget mid-chat

1. With the stack running, open `http://localhost:5173/host-test.html`.
2. Exchange at least two turns with the agent.
3. Capture the page with the widget visible and the conversation thread populated.

### Screenshot 3 — CI page with every gate green

1. Open the GitHub Actions page for the latest successful run on `main`.
2. Capture the run summary showing all gate status checks green: `lint-test-build`, `lean-image-audit`, `classifier-eval`, `rag-eval`, `agent-tool-eval`, `red-team`, `redaction-eval`, `smoke-e2e`.

**Do not `git add` any captured image file.** They live in the writeup, not in the repo.

---

## 6. Pre-merge sanity check (60 seconds)

Before opening the PR:

```powershell
git diff --name-only origin/main...HEAD
```

Expected file list (no others):

```text
README.md
RUNBOOK.md
docker-compose.yml          # only the admin->api depends_on long-form change
Makefile                    # new
scripts/check_lean_images.sh   # new
.github/workflows/ci.yml    # new job inserted between lint-test-build and the eval jobs
DECISIONS.md                # optional one-liner
specs/008-demo-polish/      # spec, plan, research, data-model, contracts, quickstart, tasks
```

If any other file appears, FR-014 is violated — back out the change before merging.
