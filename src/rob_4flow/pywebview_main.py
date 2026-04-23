# pywebview_main.py - robust launcher that waits for HTTP 200 on index.html
import threading
import time
import sys
import socket
from pathlib import Path

import webview

# CONFIG
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_PATH = "/index.html"
FLASK_URL = f"http://{FLASK_HOST}:{FLASK_PORT}{FLASK_PATH}"
HERE = Path(__file__).resolve().parent
ICON = HERE / "web" / "icon.png"
REPO_ROOT = HERE
SERVER_START_TIMEOUT = 15.0


class Api:
    def _window(self):
        if not webview.windows:
            raise RuntimeError("PyWebView window is not available yet.")
        return webview.windows[0]

    def open_graf_file(self):
        result = self._window().create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=('Excel files (*.xlsx;*.xls;*.xlsb)',)
        )
        if result:
            return result[0]
        return None

    def open_rob_file(self):
        result = self._window().create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=('ROB Files (*.rob)',)
        )
        if result:
            return result[0]
        return None

    def save_project_as(self):
        result = self._window().create_file_dialog(
            webview.FileDialog.SAVE,
            allow_multiple=False,
            file_types=('ROB Files (*.rob)',)
        )
        if not result:
            return None

        path = Path(result[0])

        if path.suffix.lower() != ".rob":
            path = path.with_suffix(".rob")

        return str(path)
    
    def export_solution(self):
        result = self._window().create_file_dialog(
            webview.FileDialog.SAVE,
            allow_multiple=False,
            file_types=('Excel (*.xlsx)',)
        )
        if not result:
            return None

        path = Path(result[0])
        
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")

        return str(path)


# Helpers
def wait_for_port(host, port, timeout=10.0):
    start = time.time()
    while True:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except Exception:
            if time.time() - start > timeout:
                return False
            time.sleep(0.1)

def http_get_status(path="/", timeout=3.0):
    import http.client
    conn = http.client.HTTPConnection(FLASK_HOST, FLASK_PORT, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        status = resp.status
        body = resp.read(4096).decode(errors="replace")
        return status, body
    except Exception as e:
        return None, str(e)
    finally:
        conn.close()


def start_flask_import():
    try:
        sys.path.insert(0, str(REPO_ROOT))
        import importlib
        module = importlib.import_module("backend.app")
        flask_app = getattr(module, "app", None)
        if not flask_app:
            raise RuntimeError("Could not find Flask 'app' in backend.app or backend/app.py")
    except Exception as e:
        raise RuntimeError(f"Import start failed: {e}")

    def _run():
        flask_app.run(host=FLASK_HOST, port=FLASK_PORT, threaded=True, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def wait_for_http_200(path=FLASK_PATH, timeout=SERVER_START_TIMEOUT):
    start_time = time.time()
    last_body = None
    while True:
        now = time.time()
        if now - start_time > timeout:
            return False, last_body
        status, body = http_get_status(path)
        last_body = body
        if status == 200:
            return True, body
        time.sleep(0.25)

def main():
    print("Launcher starting. repo_root:", REPO_ROOT)
    proc = None

    # Start Flask (try import first)
    try:
        start_flask_import()
        print("Started Flask via import (background thread).")
    except Exception as e:
        print("Import start failed:", e)

    bound = wait_for_port(FLASK_HOST, FLASK_PORT, timeout=SERVER_START_TIMEOUT/2)
    print(f"Port bind check: {bound}")

    ok, body = wait_for_http_200(path=FLASK_PATH, timeout=SERVER_START_TIMEOUT)
    print(f"HTTP 200 check for {FLASK_PATH}: {ok}")
    if ok:
        url = f"http://{FLASK_HOST}:{FLASK_PORT}{FLASK_PATH}"
        print("Opening webview to", url)
        window = webview.create_window("4flow ROB | v0", url, width=1200, height=800, resizable=True, js_api=Api())
        webview.start(on_loaded, window, debug=True, icon=ICON)
        window.events.closed += on_closed
        return

    print("Server did not return HTTP 200 for", FLASK_PATH)
    print("Last response body preview (first 200 chars):\n", (body or "")[:200])
    if proc:
        proc.terminate()

def on_loaded(window):
    window.maximize()

def on_closed():
    sys.exit()



if __name__ == "__main__":
    main()