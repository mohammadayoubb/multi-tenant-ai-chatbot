# Owner: Amer
"""Enforce SC-007 widget bundle-size budgets.

Two budgets:
- widget loader (public/widget.js, ships verbatim) ≤ 5 KB gzipped
- widget app bundle (Vite-built JS under dist/assets/) ≤ 80 KB gzipped

Both numbers come from specs/009-concierge-ui/spec.md SC-007. The check is
phrased as gzipped byte count because that is the wire-cost the visitor's
browser actually pays.

Usage:
    python scripts/check_bundle_size.py --dist frontend/widget/dist

Exit codes:
    0 - all budgets passed
    1 - at least one budget exceeded
    2 - dist directory or required artifacts missing

The CI job (`bundle-size-budget` in .github/workflows/ci.yml) runs
`npm run build` first, then this script. Lighthouse-CI would also work but its
runtime cost is two orders of magnitude higher and we only need the resource
budget, not the Lighthouse perf score.
"""

from __future__ import annotations

import argparse
import gzip
import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)

LOADER_RELATIVE = Path("widget.js")
LOADER_BUDGET_BYTES = 5 * 1024
APP_ASSETS_RELATIVE = Path("assets")
APP_BUDGET_BYTES = 80 * 1024


def gzipped_size(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), compresslevel=9))


def check(dist_dir: Path) -> int:
    if not dist_dir.is_dir():
        LOGGER.error("dist directory not found: %s", dist_dir)
        return 2

    loader = dist_dir / LOADER_RELATIVE
    if not loader.is_file():
        LOGGER.error("loader artifact missing: %s", loader)
        return 2

    assets_dir = dist_dir / APP_ASSETS_RELATIVE
    if not assets_dir.is_dir():
        LOGGER.error("assets directory missing: %s", assets_dir)
        return 2

    loader_gz = gzipped_size(loader)
    LOGGER.info(
        "loader %s gzipped=%d bytes budget=%d", loader, loader_gz, LOADER_BUDGET_BYTES
    )

    app_js_files = sorted(assets_dir.glob("*.js"))
    if not app_js_files:
        LOGGER.error("no .js files under %s", assets_dir)
        return 2

    app_gz_total = sum(gzipped_size(f) for f in app_js_files)
    LOGGER.info(
        "app js bundle files=%d gzipped_total=%d bytes budget=%d",
        len(app_js_files),
        app_gz_total,
        APP_BUDGET_BYTES,
    )
    for f in app_js_files:
        LOGGER.info("  - %s gzipped=%d bytes", f.name, gzipped_size(f))

    over_loader = loader_gz > LOADER_BUDGET_BYTES
    over_app = app_gz_total > APP_BUDGET_BYTES
    if over_loader:
        LOGGER.error(
            "loader exceeds budget: %d > %d bytes gzipped",
            loader_gz,
            LOADER_BUDGET_BYTES,
        )
    if over_app:
        LOGGER.error(
            "app js bundle exceeds budget: %d > %d bytes gzipped",
            app_gz_total,
            APP_BUDGET_BYTES,
        )
    return 1 if (over_loader or over_app) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Widget bundle-size budget check.")
    parser.add_argument(
        "--dist",
        default="frontend/widget/dist",
        help="Path to the Vite-built widget dist/ directory.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(check(Path(args.dist)))


if __name__ == "__main__":
    main()
