import subprocess
import sys
import time
import webbrowser
import os

script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.dirname(script_dir)

def check_gliner_model(python_path):
    result = subprocess.run(
        [python_path, "-c", "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_medium-v2.1')"],
        capture_output=True,
        timeout=300
    )
    return result.returncode == 0

def check_spacy_model(python_path):
    result = subprocess.run(
        [python_path, "-c", "import spacy; spacy.load('en_core_web_lg')"],
        capture_output=True
    )
    return result.returncode == 0

def get_venv_python():
    if sys.platform.startswith('win'):
        return os.path.join(script_dir, "venv", "Scripts", "python.exe")
    else:
        return os.path.join(script_dir, "venv", "bin", "python")

def ensure_venv():
    venv_python = get_venv_python()
    if not os.path.exists(venv_python):
        print("Virtual environment not found. Creating one...")
        subprocess.run([sys.executable, "-m", "venv", os.path.join(script_dir, "venv")], check=True)
        if not os.path.exists(venv_python):
            print("Error: Failed to create virtual environment.")
            sys.exit(1)
        print("Virtual environment created.")
    return venv_python

def main():
    venv_python = ensure_venv()

    print("Installing dependencies...")
    subprocess.run([venv_python, "-m", "pip", "install", "-r", os.path.join(script_dir, "backend", "requirements.txt")], check=True)

    if not check_gliner_model(venv_python):
        print("Downloading GLiNER model (first time only)...")
        subprocess.run(
            [venv_python, "-c", "from gliner import GLiNER; GLiNER.from_pretrained('urchade/gliner_medium-v2.1')"],
            check=True
        )
    else:
        print("GLiNER model already downloaded.")

    if not check_spacy_model(venv_python):
        print("Downloading spaCy model (first time only)...")
        subprocess.run([venv_python, "-m", "spacy", "download", "en_core_web_lg"], check=True)
    else:
        print("spaCy model already installed.")

    print("Starting Anon server on http://localhost:8000...")
    server_process = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=src_dir
    )

    print("Waiting for server to start...")
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)
            break
        except Exception:
            time.sleep(1)
    else:
        print("Error: Server failed to start. Check the output above.")
        server_process.terminate()
        server_process.wait()
        sys.exit(1)

    print("Opening browser...")
    webbrowser.open("http://localhost:8000")

    print("Anon is running. Press Ctrl+C to stop.")
    try:
        server_process.wait()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server_process.terminate()
        server_process.wait()
        print("Server stopped.")

if __name__ == "__main__":
    main()
