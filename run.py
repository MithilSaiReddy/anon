import subprocess
import sys
import time
import webbrowser
import os

def check_spacy_model(venv_python):
    result = subprocess.run(
        [venv_python, "-c", "import spacy; spacy.load('en_core_web_lg')"],
        capture_output=True
    )
    return result.returncode == 0

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(script_dir)
    venv_python = os.path.join(src_dir, "venv", "Scripts", "python.exe")
    
    print("Installing dependencies...")
    subprocess.run([venv_python, "-m", "pip", "install", "-r", os.path.join(script_dir, "backend", "requirements.txt")], check=True)
    
    if not check_spacy_model(venv_python):
        print("Downloading spaCy model (first time only)...")
        subprocess.run([venv_python, "-m", "spacy", "download", "en_core_web_lg"], check=True)
    else:
        print("spaCy model already installed.")
    
    print("Starting Anon server on http://localhost:8000...")
    server_process = subprocess.Popen(
        [venv_python, "-m", "uvicorn", "anon.backend.main:app", "--host", "127.0.0.1", "--port", "8000", "--reload"],
        cwd=src_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    time.sleep(3)
    
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