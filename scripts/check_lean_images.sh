#!/usr/bin/env bash
# Owner: Amer
#
# Lean-image audit — enforces Constitution Principle V:
#   "Serving containers (modelserver, guardrails) MUST NOT include torch or transformers."
#
# Contract: specs/008-demo-polish/contracts/lean-image-audit-cli.md
#
# Default behavior (no flags): audit the modelserver and guardrails images
# built by `docker compose build` for the two forbidden packages.

set -u

DEFAULT_IMAGES=(
  "multi-tenant-ai-chatbot-modelserver"
  "multi-tenant-ai-chatbot-guardrails"
)
DEFAULT_PACKAGES=(
  "torch"
  "transformers"
)

# Hardcoded image -> compose service map, used only to make the "image not
# found" hint actionable for the default image set. Images supplied via
# --image that are not in this map fall back to a generic build hint.
service_hint_for() {
  case "$1" in
    multi-tenant-ai-chatbot-modelserver) echo "modelserver" ;;
    multi-tenant-ai-chatbot-guardrails)  echo "guardrails"  ;;
    *) echo "" ;;
  esac
}

usage() {
  cat <<'EOF'
Usage: check_lean_images.sh [--image <name>]... [--package <regex>]... [-h|--help]

Audits docker images for forbidden Python packages. Default image set is
modelserver+guardrails; default forbidden set is torch+transformers.

Exit codes:
  0   clean
  1   violation (one or more forbidden packages found)
  2   setup error (image not found locally, or docker not on PATH)
  64  usage error
EOF
}

IMAGES=()
PACKAGES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "lean-image-audit: --image requires a non-empty value" >&2
        usage >&2
        exit 64
      fi
      IMAGES+=("$2")
      shift 2
      ;;
    --package)
      if [[ $# -lt 2 || -z "${2:-}" ]]; then
        echo "lean-image-audit: --package requires a non-empty value" >&2
        usage >&2
        exit 64
      fi
      PACKAGES+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "lean-image-audit: unknown flag '$1'" >&2
      usage >&2
      exit 64
      ;;
    *)
      echo "lean-image-audit: positional arguments are not accepted ('$1')" >&2
      usage >&2
      exit 64
      ;;
  esac
done

if [[ ${#IMAGES[@]} -eq 0 ]]; then
  IMAGES=("${DEFAULT_IMAGES[@]}")
fi
if [[ ${#PACKAGES[@]} -eq 0 ]]; then
  PACKAGES=("${DEFAULT_PACKAGES[@]}")
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "lean-image-audit: docker not found on PATH" >&2
  exit 2
fi

violations=()

for image in "${IMAGES[@]}"; do
  if ! docker image inspect "$image" >/dev/null 2>&1; then
    hint="$(service_hint_for "$image")"
    if [[ -n "$hint" ]]; then
      echo "lean-image-audit: image not found: ${image}. Run 'docker compose build ${hint}' first." >&2
    else
      echo "lean-image-audit: image not found: ${image}. Build it first." >&2
    fi
    exit 2
  fi

  pip_output="$(docker run --rm --entrypoint pip "$image" list --format=freeze 2>/dev/null)"
  rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "lean-image-audit: failed to run 'pip list' inside ${image} (exit ${rc})" >&2
    exit 2
  fi

  for pkg in "${PACKAGES[@]}"; do
    regex="^${pkg}([=[:space:]]|$)"
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      if printf '%s\n' "$line" | grep -Eiq "$regex"; then
        violations+=("${image}: forbidden package ${pkg} (matched: ${line})")
      fi
    done <<<"$pip_output"
  done
done

if [[ ${#violations[@]} -gt 0 ]]; then
  {
    echo "lean-image-audit: VIOLATION"
    for v in "${violations[@]}"; do
      echo "  ${v}"
    done
    echo "Constitution Principle V forbids torch and transformers in serving containers."
  } >&2
  exit 1
fi

echo "lean-image-audit: clean (${#IMAGES[@]} images, ${#PACKAGES[@]} regexes)"
exit 0
