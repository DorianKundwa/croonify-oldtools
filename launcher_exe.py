import os
import sys
import time
import socket
import threading
import subprocess
import webbrowser
from http.server import SimpleHTTPRequestHandler
from socketserver import ThreadingTCPServer
from functools import partial
from pathlib import Path


def find_python():
    candidates = [
        ['python'],
        ['py', '-3'],
        ['py']
    ]
    for cmd in candidates:
        try:
            subprocess.run(cmd + ['--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
            return cmd
        except Exception:
            continue
    return None


def wait_for_port(port, host='127.0.0.1', timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def start_frontend_server(frontend_dir: Path, port: int = 5500):
    handler = partial(SimpleHTTPRequestHandler, directory=str(frontend_dir))
    ThreadingTCPServer.allow_reuse_address = True
    httpd = ThreadingTCPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def main():
    FRONTEND_PORT = int(os.environ.get('CROONIFY_FRONTEND_PORT', '5500'))
    BACKEND_PORT = int(os.environ.get('CROONIFY_BACKEND_PORT', '5000'))

    # Assume the EXE is run from the project root; fall back to exe location
    root = Path.cwd()
    if not (root / 'backend').exists() or not (root / 'frontend').exists():
        if getattr(sys, 'frozen', False):
            root = Path(sys.executable).parent
        else:
            root = Path(__file__).parent.resolve()

    backend_dir = root / 'backend'
    frontend_dir = root / 'frontend'

    python_cmd = find_python()
    if python_cmd is None:
        print('Error: Could not find Python interpreter on PATH. Please install Python 3.9+ and ensure it is on PATH.')
        sys.exit(1)

    # Start backend
    backend_proc = subprocess.Popen(python_cmd + [str(backend_dir / 'app.py')], cwd=str(backend_dir))

    # Start frontend static server
    httpd = start_frontend_server(frontend_dir, FRONTEND_PORT)

    # Wait for backend port
    if wait_for_port(BACKEND_PORT, '127.0.0.1', timeout=30):
        url = f'http://localhost:{FRONTEND_PORT}/'
        print(f'Frontend: {url}')
        print(f'Backend: http://localhost:{BACKEND_PORT}/')
        try:
            webbrowser.open(url)
        except Exception:
            pass
    else:
        print('Warning: Backend did not become ready within 30s')

    try:
        print('Press Ctrl+C to stop')
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception:
            pass
        try:
            backend_proc.terminate()
        except Exception:
            pass


if __name__ == '__main__':
    main()