"""brief.md -> brief.pdf. Markdown is rendered to styled HTML (python-markdown) and printed by whatever
Chromium-family browser is installed (Chrome, Chromium, Edge), headless, with a throwaway profile so a
running browser is never touched. No browser: the PDF is skipped and the reason is reported."""
import os
import shutil
import subprocess
import sys
import tempfile

CSS = """
@page { size: Letter; margin: 0.55in 0.6in; }
body { font-family: Calibri, "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; line-height: 1.38; color: #111; }
h1 { font-size: 20pt; margin: 0 0 6pt; color: #0b2545; }
h2 { font-size: 13.5pt; margin: 18pt 0 6pt; padding-bottom: 3pt; border-bottom: 1.5px solid #0b2545; color: #0b2545; page-break-after: avoid; }
h3 { font-size: 11pt; margin: 12pt 0 4pt; color: #333; page-break-after: avoid; }
p { margin: 0 0 7pt; }
ul { margin: 0 0 7pt 0; padding-left: 18pt; }
li { margin-bottom: 2pt; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 10pt; font-size: 8.6pt; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #c9ced6; padding: 2.5pt 4pt; text-align: left; vertical-align: top; }
th { background: #e8edf5; font-weight: 600; }
tbody tr:nth-child(even) td { background: #f6f8fb; }
td:first-child, th:first-child { white-space: nowrap; }
strong { color: #0b2545; }
code { font-family: Consolas, Menlo, monospace; font-size: 9pt; background: #f1f3f6; padding: 0 2pt; }
"""

CANDIDATES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge", "microsoft-edge"]
WINDOWS_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]
MAC_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def find_browser():
    env = os.environ.get("REBUILD_BROWSER")
    if env and os.path.exists(env):
        return env
    for name in CANDIDATES:
        p = shutil.which(name)
        if p:
            return p
    local = os.environ.get("LOCALAPPDATA", "")
    extra = [os.path.join(local, r"Google\Chrome\Application\chrome.exe")] if local else []
    for p in (WINDOWS_PATHS + extra if os.name == "nt" else MAC_PATHS):
        if os.path.exists(p):
            return p
    return None


def to_html(md_text, title):
    import markdown  # python-markdown; in requirements.txt
    body = markdown.markdown(md_text, extensions=["tables", "sane_lists"])
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>"


def render(md_path, pdf_path, timeout=180):
    """Returns (pdf_path, None) on success or (None, reason)."""
    try:
        with open(md_path, encoding="utf-8") as f:
            html = to_html(f.read(), os.path.splitext(os.path.basename(md_path))[0])
    except ImportError:
        return None, "python-markdown is not installed (pip install markdown)"
    browser = find_browser()
    if not browser:
        return None, "no Chrome, Chromium or Edge found (set REBUILD_BROWSER to the executable to use)"
    work = tempfile.mkdtemp(prefix="rebuild-pdf-")
    src = os.path.join(work, "brief.html")
    with open(src, "w", encoding="utf-8") as f:
        f.write(html)
    pdf_path = os.path.abspath(pdf_path)
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--disable-extensions",
           f"--user-data-dir={os.path.join(work, 'profile')}", "--no-pdf-header-footer",
           f"--print-to-pdf={pdf_path}", "file:///" + src.replace(os.sep, "/").lstrip("/")]
    if sys.platform.startswith("linux"):
        cmd.insert(1, "--no-sandbox")   # containers and CI runners
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"browser failed: {e}"
    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
        tail = (r.stderr or "")[-300:].strip()
        return None, f"browser exited {r.returncode} without writing the PDF" + (f": {tail}" if tail else "")
    shutil.rmtree(work, ignore_errors=True)
    return pdf_path, None
