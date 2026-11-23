"""Zip the engine for the browser: rebuild/*.py minus what needs the network, disk or a terminal, plus the shipped benchmarks.

    python3 web/scripts/build_engine.py [--out PATH]"""
import argparse
import glob
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXCLUDE = {"cli.py", "__main__.py", "fetch.py", "sleeper.py", "inputs.py", "pdf.py"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "web", "public", "engine", "engine.zip"))
    a = ap.parse_args(argv)
    files = [(p, f"rebuild/{os.path.basename(p)}") for p in sorted(glob.glob(os.path.join(ROOT, "rebuild", "*.py")))
             if os.path.basename(p) not in EXCLUDE]
    files += [(p, f"benchmarks/{os.path.basename(p)}") for p in sorted(glob.glob(os.path.join(ROOT, "benchmarks", "*.json")))]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        for src, name in files:
            z.write(src, name)
    print(f"{len(files)} files, {os.path.getsize(a.out)} bytes -> {a.out}")


if __name__ == "__main__":
    main()
