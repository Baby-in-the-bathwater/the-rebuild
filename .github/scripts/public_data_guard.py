"""Fail if anything that looks like private league data is committed to this public repo.

The repo ships code and aggregate benchmark tables only: no Sleeper league ids, no run output,
no cached league pulls. This scans every tracked file and exits 1 with the offending lines.

    python .github/scripts/public_data_guard.py
"""
import re
import subprocess
import sys

# Sleeper league, roster-owner and draft ids are 17-20 digit integers. Decimals (benchmark
# coefficients) are excluded by refusing a neighboring digit or dot.
LONG_ID = re.compile(r"(?<![\d.])\d{17,20}(?![\d.])")
ALLOWED_IDS = {"123456789012345678"}  # the README's placeholder
BLOCKED_DIRS = ("out/", "cache/")  # run output and cached pulls (also gitignored)
SKIP_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".ico", ".woff", ".woff2", ".ttf")


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def main() -> int:
    problems = []
    for path in tracked_files():
        if path.startswith(BLOCKED_DIRS):
            problems.append(f"{path}: run output or cache must never be committed")
            continue
        if path.lower().endswith(SKIP_SUFFIXES):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    for m in LONG_ID.finditer(line):
                        if m.group() not in ALLOWED_IDS:
                            problems.append(f"{path}:{n}: looks like a Sleeper id ({m.group()})")
        except UnicodeDecodeError:
            continue
    if problems:
        print("Public-data guard FAILED. This repo is public: no league ids, rosters, manager names or run output.")
        print("\n".join(problems))
        return 1
    print("Public-data guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
