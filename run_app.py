import sys
import os
import time
import threading
import socket
import subprocess
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
BACKEND_PORT = 5000
FRONTEND_PORT = 5500

def wait_for_port(port, host="127.0.0.1", timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        s = socket.socket()
        s.settimeout(0.5)
        try:
            s.connect((host, port))
            s.close()
            return True
        except Exception:
            pass
        finally:
            s.close()
        time.sleep(0.5)
    return False

def start_backend():
    return subprocess.Popen([sys.executable, "app.py"], cwd=str(BACKEND_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

def start_frontend_server():
    handler = partial(SimpleHTTPRequestHandler, directory=str(FRONTEND_DIR))
    httpd = ThreadingHTTPServer(("127.0.0.1", FRONTEND_PORT), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd

def main():
    backend = start_backend()
    wait_for_port(BACKEND_PORT, timeout=30)
    frontend = start_frontend_server()
    url = f"http://localhost:{FRONTEND_PORT}/"
    webbrowser.open(url)
    print("Frontend:", url)
    print("Backend:", f"http://localhost:{BACKEND_PORT}/")
    try:
        while True:
            line = backend.stdout.readline()
            if not line:
                break
            sys.stdout.write(line.decode(errors="ignore"))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            frontend.shutdown()
        except Exception:
            pass
        try:
            backend.terminate()
            backend.wait(timeout=5)
        except Exception:
            pass

if __name__ == "__main__":
    main()