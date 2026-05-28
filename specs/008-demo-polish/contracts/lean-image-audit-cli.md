# Contract: Lean Image Audit CLI

**File**: `scripts/check_lean_images.sh`
**Entry point in Makefile**: `make lean-image-audit`
**Owner**: Amer
**Enforces**: Constitution Principle V — "Serving containers (`modelserver`, `guardrails`) MUST NOT include `torch` or `transformers`."

This contract is the source of truth for the lean-image audit tool. CI, the Makefile, contributors, and any future re-implementation of the audit MUST conform to this contract.

---

## 1. Invocation

```text
check_lean_images.sh [--image <image-name>]... [--package <regex>]... [-h|--help]
```

With no flags, the script audits the two images named in section 2 against the two packages named in section 3 — i.e., the default behavior matches the constitutional rule exactly.

### Flags

| Flag | Repeatable | Default | Purpose |
|------|------------|---------|---------|
| `--image <name>` | yes | `multi-tenant-ai-chatbot-modelserver`, `multi-tenant-ai-chatbot-guardrails` | Override the image set being audited. Used by tests and future reuse. |
| `--package <regex>` | yes | `torch`, `transformers` | Override the forbidden-package regex set. Each value is compiled as a case-insensitive anchored regex with the boundary `([=\s]\|$)` appended. |
| `-h`, `--help` | no | — | Print usage and exit 0. |

The script MUST NOT accept any positional arguments.

---

## 2. Default Image Set

| Image | Compose service | Constitutional reason |
|-------|-----------------|------------------------|
| `multi-tenant-ai-chatbot-modelserver` | `modelserver` | Serving container — must use ONNXRuntime / scikit-learn only. |
| `multi-tenant-ai-chatbot-guardrails` | `guardrails` | Serving container — sidecar; must not pull DL frameworks. |

The image names match the default tags produced by `docker compose build` from this repo's `docker-compose.yml`. If the project name changes (via `COMPOSE_PROJECT_NAME` or directory rename), the caller MUST pass `--image` explicitly.

---

## 3. Default Forbidden-Package Regex Set

| Regex (anchored, case-insensitive) | Catches |
|------------------------------------|---------|
| `^torch([=\s]\|$)` | `torch`, `torch==2.x`, `torch 2.x` (column format). Does NOT match `torchvision` directly — but `torchvision` cannot land without `torch`, so the `torch` row will trigger. |
| `^transformers([=\s]\|$)` | `transformers`, `transformers==4.x`. Does NOT match `transformers-extensions-mock` etc. |

The boundary `([=\s]|$)` exists because `pip list --format=freeze` produces `name==version` (no space) while `pip list` (column format) produces `name<spaces>version`. Both shapes are tolerated.

---

## 4. Execution Steps (normative)

For each image in the image set, the script MUST:

1. Verify the image exists locally: `docker image inspect <image> > /dev/null 2>&1`. If absent, exit 2 with message `lean-image-audit: image not found: <image>. Run 'docker compose build <service>' first.` where `<service>` is derived via the hardcoded map `{multi-tenant-ai-chatbot-modelserver: modelserver, multi-tenant-ai-chatbot-guardrails: guardrails}`. For images passed via `--image` that are not in the map, fall back to the message `lean-image-audit: image not found: <image>. Build it first.` (no per-service hint).
2. Run: `docker run --rm --entrypoint pip <image> list --format=freeze`. Capture stdout.
3. For each forbidden-package regex, scan the captured stdout case-insensitively for a matching line.
4. If any match is found, record `<image>: forbidden package <name> (matched: <full line>)` and continue scanning the rest of the regexes for that image (so the failure report names every offender, not just the first).
5. After all images are scanned, if any matches were recorded, print the full list of offenders to stderr and exit 1.
6. If no matches were found across all images, print `lean-image-audit: clean (<N> images, <M> regexes)` to stdout and exit 0.

The script MUST NOT modify either image. It MUST NOT push, tag, or commit anything.

---

## 5. Exit Codes

| Code | Meaning | When |
|------|---------|------|
| 0 | Clean | No forbidden package found in any audited image. |
| 1 | Violation | At least one forbidden package found. Failure message names image(s) and package(s). |
| 2 | Setup error | A required image was not found locally, or `docker` is not on PATH. |
| 64 | Usage error | Unknown flag, positional argument, or `--image` / `--package` with empty value. |

---

## 6. Output Format

### Success (exit 0, stdout)

```text
lean-image-audit: clean (2 images, 2 regexes)
```

### Violation (exit 1, stderr)

```text
lean-image-audit: VIOLATION
  multi-tenant-ai-chatbot-modelserver: forbidden package torch (matched: torch==2.3.1)
  multi-tenant-ai-chatbot-modelserver: forbidden package transformers (matched: transformers==4.41.0)
Constitution Principle V forbids torch and transformers in serving containers.
```

### Setup error (exit 2, stderr)

```text
lean-image-audit: image not found: multi-tenant-ai-chatbot-modelserver. Run 'docker compose build modelserver' first.
```

### Usage error (exit 64, stderr)

```text
lean-image-audit: unknown flag '--foo'
Usage: check_lean_images.sh [--image <name>]... [--package <regex>]... [-h|--help]
```

---

## 7. CI Integration

The new job in `.github/workflows/ci.yml`:

```yaml
lean-image-audit:
  needs: lint-test-build
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Build serving images
      run: docker compose build modelserver guardrails
    - name: Audit serving images for torch/transformers
      run: make lean-image-audit
```

The job MUST be wired into CI such that its failure status is surfaced as a required check (branch protection configuration, out of scope for this PR).

---

## 8. Test Plan

| Test | Setup | Expected exit | Expected output substring |
|------|-------|---------------|---------------------------|
| Happy path | Build clean modelserver and guardrails images | 0 | `lean-image-audit: clean` |
| Forbidden package present | Build modelserver with `RUN pip install torch` added | 1 | `forbidden package torch` |
| Image missing | No build performed | 2 | `image not found` |
| Unknown flag | Run `check_lean_images.sh --foo` | 64 | `unknown flag` |
| Custom image clean | Audit a known-clean image via `--image python:3.11-slim` | 0 | `clean` |

The "forbidden package present" test does NOT need to live in the repo; it is a manual verification step the script's author runs once and records in the PR description. (Permanently committing a Dockerfile that imports `torch` would itself violate Principle V.)
