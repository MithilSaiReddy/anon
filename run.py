#!/usr/bin/env python3
"""
Cross-platform launcher for the NER web app.
Works on Linux, macOS, and Windows.
"""

import subprocess
import sys
import time
import webbrowser
import os
import shutil

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR   = os.path.join(SCRIPT_DIR, "venv")
MODELS_DIR = os.path.join(SCRIPT_DIR, "models")

IS_WINDOWS = sys.platform.startswith("win")


# ── Virtual-environment helpers ────────────────────────────────────────────────

def find_venv_python():
    """Return the path to the Python executable inside the venv."""
    if IS_WINDOWS:
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python3")


def find_system_python():
    """Return the first usable system Python interpreter."""
    candidates = (["python3", "python"]
                  if not IS_WINDOWS else
                  ["python", "python3", "py"])
    for name in candidates:
        exe = shutil.which(name)
        if exe:
            # Make sure it is Python 3
            try:
                r = subprocess.run(
                    [exe, "-c", "import sys; assert sys.version_info >= (3,8)"],
                    capture_output=True
                )
                if r.returncode == 0:
                    return exe
            except Exception:
                continue

    # Last resort: the interpreter running this very script
    if sys.executable:
        return sys.executable

    print("ERROR: No Python 3.8+ interpreter found on PATH.")
    sys.exit(1)


def ensure_venv():
    """Create (or re-use) a venv and return the path to its Python binary."""
    venv_python = find_venv_python()

    # Re-use existing venv if pip is functional inside it
    if os.path.exists(venv_python):
        r = subprocess.run([venv_python, "-m", "pip", "--version"],
                           capture_output=True)
        if r.returncode == 0:
            print("Using existing virtual environment.")
            return venv_python
        print("Existing venv is broken — recreating …")
        shutil.rmtree(VENV_DIR, ignore_errors=True)

    python_exe = find_system_python()
    print(f"Using system Python: {python_exe}")

    # Verify ensurepip is available (absent on some Debian/Ubuntu packages)
    check = subprocess.run(
        [python_exe, "-c", "import ensurepip; ensurepip.version()"],
        capture_output=True
    )
    if check.returncode != 0:
        major = sys.version_info.major
        minor = sys.version_info.minor
        venv_pkg = f"python{major}.{minor}-venv"
        print(
            "\nERROR: 'ensurepip' is unavailable (required to create a venv).\n"
            "Install it with:\n"
            f"  Debian/Ubuntu : sudo apt install {venv_pkg}\n"
            f"  Fedora        : sudo dnf install python3-virtualenv\n"
            f"  Arch          : sudo pacman -S python-virtualenv\n"
            f"  Windows       : reinstall Python from https://python.org "
            f"and tick 'pip' during setup\n"
        )
        sys.exit(1)

    # Create the venv WITHOUT bundled pip (we bootstrap it ourselves so the
    # version is always fresh and the step works even offline distros)
    print(f"Creating virtual environment at {VENV_DIR} …")
    subprocess.run([python_exe, "-m", "venv", "--without-pip", VENV_DIR],
                   check=True)

    if not os.path.exists(venv_python):
        print(f"ERROR: venv was not created at {VENV_DIR}")
        sys.exit(1)

    print("Bootstrapping pip …")
    subprocess.run(
        [venv_python, "-m", "ensurepip", "--upgrade", "--default-pip"],
        check=True, capture_output=True
    )

    print("Virtual environment ready.")
    return venv_python


# ── Package installation ───────────────────────────────────────────────────────

def run_pip(venv_python, *args):
    """Upgrade pip then install the requested packages."""
    subprocess.run(
        [venv_python, "-m", "pip", "install", "--upgrade", "pip"],
        capture_output=True   # silently upgrade pip
    )
    subprocess.run(
        [venv_python, "-m", "pip", "install", "--default-timeout=120"] + list(args),
        check=True
    )


# ── Model availability checks ─────────────────────────────────────────────────

def gliner_is_available(venv_python):
    """Return True when the GLiNER model is already cached locally."""
    cmd = (
        "from gliner import GLiNER; "
        f"GLiNER.from_pretrained('urchade/gliner_medium-v2.1', "
        f"cache_dir={repr(MODELS_DIR)})"
    )
    try:
        r = subprocess.run(
            [venv_python, "-c", cmd],
            capture_output=True, timeout=300
        )
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


SPACY_LG_URL = "https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl"
SPACY_SM_URL = "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"

def spacy_is_available(venv_python, model="en_core_web_lg"):
    """Return True when a spaCy model is installed."""
    try:
        r = subprocess.run(
            [venv_python, "-c",
             f"import spacy; spacy.load('{model}')"],
            capture_output=True, timeout=120
        )
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


# ── Server health-check ────────────────────────────────────────────────────────

def wait_for_server(url: str, retries: int = 40, delay: float = 1.0) -> bool:
    """
    Poll *url* until it responds with HTTP 200 (or any non-error).
    Returns True on success, False on timeout.
    """
    import urllib.request, urllib.error

    for attempt in range(1, retries + 1):
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except urllib.error.HTTPError as exc:
            # An HTTP error still means the server is up
            if exc.code < 500:
                return True
        except Exception:
            pass
        time.sleep(delay)

    return False


# ── Entry-point ────────────────────────────────────────────────────────────────

def main():
    os.chdir(SCRIPT_DIR)
    os.makedirs(MODELS_DIR, exist_ok=True)

    print("=" * 60)
    print(f"  Project : {SCRIPT_DIR}")
    print(f"  Models  : {MODELS_DIR}")
    print(f"  Platform: {sys.platform}")
    print("=" * 60)

    # ── Step 1 — venv ──────────────────────────────────────────────────────────
    venv_python = ensure_venv()

    # ── Step 2 — Python dependencies ──────────────────────────────────────────
    requirements_path = os.path.join(SCRIPT_DIR, "backend", "requirements.txt")
    if not os.path.exists(requirements_path):
        print(f"ERROR: requirements file not found: {requirements_path}")
        sys.exit(1)

    print("Installing Python dependencies …")
    run_pip(venv_python, "-r", requirements_path)

    # ── Step 3 — ML models ────────────────────────────────────────────────────
    # Tell HuggingFace where to cache models so they survive across runs
    os.environ["HF_HOME"]      = MODELS_DIR
    os.environ["HF_HUB_CACHE"] = os.path.join(MODELS_DIR, "hub")

    if not gliner_is_available(venv_python):
        print("Downloading GLiNER model (~200 MB) — this takes a few minutes …")
        cmd = (
            "from gliner import GLiNER; "
            f"GLiNER.from_pretrained('urchade/gliner_medium-v2.1', "
            f"cache_dir={repr(MODELS_DIR)})"
        )
        subprocess.run([venv_python, "-c", cmd], check=True, timeout=600)
    else:
        print("GLiNER model : ready")

    if not spacy_is_available(venv_python):
        print("Downloading spaCy model (en_core_web_lg ~500 MB) …")
        try:
            subprocess.run(
                [venv_python, "-m", "pip", "install", "--default-timeout=600", SPACY_LG_URL],
                check=True, timeout=900
            )
            print("spaCy model  : ready (en_core_web_lg)")
        except Exception:
            print("en_core_web_lg download failed, trying smaller model (en_core_web_sm ~12 MB) …")
            try:
                subprocess.run(
                    [venv_python, "-m", "pip", "install", "--default-timeout=300", SPACY_SM_URL],
                    check=True, timeout=600
                )
                print("spaCy model  : ready (en_core_web_sm)")
            except Exception:
                print("WARNING: Could not download any spaCy model. Server will run with GLiNER only.")
    else:
        print("spaCy model  : ready")

    # ── Step 4 — Start uvicorn ─────────────────────────────────────────────────
    host = "127.0.0.1"
    port = 8000
    url  = f"http://{host}:{port}"

    print(f"\nStarting server at {url} …")

    server_env = os.environ.copy()
    server_env["PYTHONDONTWRITEBYTECODE"] = "1"

    # On Windows, subprocess.Popen needs shell=False and a list-form command —
    # both already satisfied here.  CREATE_NEW_PROCESS_GROUP lets us send
    # Ctrl-C cleanly on Windows without killing the launcher itself.
    popen_kwargs = dict(cwd=SCRIPT_DIR, env=server_env)
    if IS_WINDOWS:
        import signal as _signal
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    server = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "backend.main:app",
         "--host", host, "--port", str(port)],
        **popen_kwargs
    )

    print("Waiting for server to become ready …", end="", flush=True)
    if wait_for_server(f"{url}/health"):
        print(" OK")
    else:
        print(" TIMEOUT")
        print("ERROR: Server did not start within the expected time.")
        server.terminate()
        server.wait()
        sys.exit(1)

    # ── Step 5 — Open browser ──────────────────────────────────────────────────
    try:
        webbrowser.open(url)
    except Exception:
        print(f"Could not open browser automatically. Visit {url} manually.")

    print(f"\nApp running at {url}")
    print("Press Ctrl+C to stop.\n")

    # ── Step 6 — Wait for server / handle Ctrl-C ──────────────────────────────
    try:
        server.wait()
    except KeyboardInterrupt:
        print("\nShutting down …")
        if IS_WINDOWS:
            # On Windows send CTRL_BREAK_EVENT to the process group
            import signal
            try:
                os.kill(server.pid, signal.CTRL_BREAK_EVENT)
            except Exception:
                server.terminate()
        else:
            server.terminate()
        server.wait()
        print("Stopped.")


if __name__ == "__main__":
    main()