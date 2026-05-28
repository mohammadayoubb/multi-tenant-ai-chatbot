# Owner: Amer
# Single entry point for Amer-owned operational checks.
# Each target is a thin wrapper around a script under scripts/, so the same
# command works on developer machines and in CI.

.PHONY: lean-image-audit

lean-image-audit:
	bash scripts/check_lean_images.sh
