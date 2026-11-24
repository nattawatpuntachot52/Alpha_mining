#!/usr/bin/env python3
"""Build the unified central GitHub Pages portal (`index.html`) separating Alpha & Beta tracks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = REPO_ROOT / "python"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from alpha_mining.research.portal_hub import (  # noqa: E402
    collect_unified_portal_payload,
    render_unified_portal_html,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build unified Alpha + Beta central portal index.html for GitHub Pages."
    )
    parser.add_argument("--alpha-dir", type=Path, default=REPO_ROOT / "alpha_mining")
    parser.add_argument("--beta-dir", type=Path, default=REPO_ROOT / "beta_mining")
    parser.add_argument("--alpha-prefix", default="alpha")
    parser.add_argument("--beta-prefix", default="beta")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    payload = collect_unified_portal_payload(
        alpha_dir=args.alpha_dir,
        beta_dir=args.beta_dir,
        alpha_prefix=args.alpha_prefix,
        beta_prefix=args.beta_prefix,
    )
    html_text = render_unified_portal_html(payload)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html_text, encoding="utf-8", newline="\n")
    print(
        f"Built unified portal {args.out} "
        f"(Alpha: {payload['alpha']['total_models']} models / {payload['alpha']['total_days']}d, "
        f"Beta: {payload['beta']['total_models']} models / {payload['beta']['total_days']}d)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
