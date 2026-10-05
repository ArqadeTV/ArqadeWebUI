#!/usr/bin/env python3
"""Install Arqade's libraries one package at a time so a single failure never blocks the rest.

    python scripts/install_all.py --profile lite|standard|full [--dry-run]

Profiles come from arqade/libs.py (stdlib-only, so this runs before anything is installed).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from arqade import libs  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=libs.PROFILES, default="standard")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    todo = [lib for lib in libs.select(args.profile) if libs.installed_version(lib) is None]
    skipped = [lib.pip for lib in libs.LIBRARIES if not libs.applicable(lib) and libs.in_profile(lib, args.profile)]
    print(f"Profile '{args.profile}': {len(todo)} to install, "
          f"{len(libs.select(args.profile)) - len(todo)} already present"
          + (f", {len(skipped)} not applicable on this OS" if skipped else ""))
    if args.dry_run:
        print("\n".join(f"  - {lib.pip}" for lib in todo))
        return 0

    ok, failed = [], []
    t0 = time.time()
    for n, lib in enumerate(todo, 1):
        print(f"\n[{n}/{len(todo)}] pip install {lib.pip}  ({lib.desc})", flush=True)
        rc = subprocess.call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", lib.pip])
        (ok if rc == 0 else failed).append(lib.pip)
        print("   ok" if rc == 0 else "   FAILED - skipping (you can retry from the Libraries tab)", flush=True)

    print(f"\nDone in {time.time() - t0:.0f}s: {len(ok)} installed, {len(failed)} failed")
    if failed:
        print("Failed: " + ", ".join(failed))
        print("Usually these need a newer/older Python or a C++ compiler. Arqade still works without them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
