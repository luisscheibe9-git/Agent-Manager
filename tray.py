"""Chat inbox tray app: runs the inbox server and a system-tray icon with an unread badge.
Left-click opens the inbox as a Chrome app window. Run with pythonw (no console)."""
import ctypes
import os
import subprocess
import sys
import threading
import time
import shutil
from http.server import ThreadingHTTPServer
from ctypes import wintypes

import pystray
from PIL import Image, ImageDraw, ImageFont

import inbox
import taskbar
import dashboard

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = shutil.which("chrome") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = f"http://localhost:{inbox.PORT}"
PROFILE = os.environ.get("AGENT_MANAGER_PROFILE_DIR", os.path.join(inbox.DATA_DIR, "chrome_profile"))
WINDOW_TITLE = os.environ.get("AGENT_MANAGER_LABEL")
BASE = Image.open(os.path.join(HERE, "inbox.ico")).convert("RGBA")  # largest entry
if BASE.size[0] < 128:
    BASE = Image.open(os.path.join(HERE, "inbox_512.png")).convert("RGBA")
BASE = BASE.resize((128, 128), Image.LANCZOS)


def with_badge(n):
    im = BASE.copy()
    if n:
        d = ImageDraw.Draw(im)
        d.ellipse([62, 62, 128, 128], fill=(220, 38, 38, 255), outline=(255, 255, 255, 255), width=5)
        text = str(n) if n < 100 else "99+"
        try:
            font = ImageFont.truetype("arialbd.ttf", 44 if n < 10 else 34)
        except OSError:
            font = ImageFont.load_default()
        d.text((95, 95), text, fill="white", font=font, anchor="mm")
    return im


keep_open = [dashboard.settings()["keep_taskbar"]]
STOP = threading.Event()
restart_requested = [False]


def toggle_keep(icon, item):
    keep_open[0] = not keep_open[0]
    dashboard.update_settings({"keep_taskbar": keep_open[0]})


def open_window(*_):
    """Focus the existing inbox window, or start one. Never opens a second window."""
    hwnd = taskbar.find_window(WINDOW_TITLE)
    if hwnd:
        taskbar.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        taskbar.user32.SetForegroundWindow(hwnd)
        return
    last_open[0] = time.time()
    subprocess.Popen([CHROME, f"--app={URL}", f"--user-data-dir={PROFILE}"])


def mark_all(icon, *_):
    dashboard.action("mark-all", {})
    refresh(icon)


def badge_only(n):
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([2, 2, 62, 62], fill=(220, 38, 38, 255))
    text = str(n) if n < 100 else "99+"
    try:
        font = ImageFont.truetype("arialbd.ttf", 38 if n < 10 else 30 if n < 100 else 24)
    except OSError:
        font = ImageFont.load_default()
    d.text((32, 33), text, fill="white", font=font, anchor="mm")
    return im


def window_open():
    return taskbar.find_window(WINDOW_TITLE) is not None


def open_minimized():
    si = subprocess.STARTUPINFO()
    si.dwFlags = subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
    subprocess.Popen([CHROME, f"--app={URL}", f"--user-data-dir={PROFILE}"], startupinfo=si)


last_open = [0.0]
server = {"thread": None, "http": None}


def start_server():
    """(Re)start the web server thread; harmless if the port is already served by another copy."""
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", inbox.PORT), inbox.H)
    except OSError:
        return
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    server["thread"] = t
    server["http"] = srv
    inbox.log("server started")


def refresh(icon):
    data = dashboard.snapshot()
    n = data["counts"]["todo"]
    icon.icon = with_badge(n)
    icon.title = f"Agent Manager: {n} need attention" if n else "Agent Manager: all caught up"
    hwnd = taskbar.find_window(WINDOW_TITLE)
    if hwnd is None:
        pass  # window closed on purpose: stay closed; the tray icon still carries the count
    else:
        taskbar.set_badge(hwnd, badge_only(n) if n else None, f"{n} unread")
        taskbar.brand_window(hwnd, CHROME, URL, PROFILE, os.path.join(HERE, "inbox.ico"))


def loop(icon):
    icon.visible = True
    while icon.visible and not STOP.is_set():
        try:
            t = server["thread"]
            if t is None or not t.is_alive():
                start_server()  # watchdog: the server must always be up
            refresh(icon)
            dashboard.notify_due(icon.notify)
            keep_open[0] = dashboard.settings()["keep_taskbar"]
        except Exception as e:  # never let the loop die
            inbox.log("tray loop error: " + repr(e))
        STOP.wait(5)


_mutex = None


def already_running():
    """Single instance: a named mutex, so Task Scheduler can relaunch freely without duplicates."""
    global _mutex
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    name = "ChatInboxTrayMutex" if inbox.PORT == 8765 else f"AgentManagerTray{inbox.PORT}"
    _mutex = kernel32.CreateMutexW(None, False, name)
    error = ctypes.get_last_error()
    if not _mutex:
        raise ctypes.WinError(error)
    return error == 183  # ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    if already_running():
        if "--open" in sys.argv:  # a shortcut/pin was used while the tray runs: just focus the window
            try:
                import urllib.request
                urllib.request.urlopen(URL + "/open", timeout=3)
            except Exception:
                pass
        sys.exit()
    start_server()
    inbox.ON_OPEN = open_window
    def control(command):
        restart_requested[0] = command == "restart"
        STOP.set()
        icon.stop()
    inbox.ON_CONTROL = control
    if "--open" in sys.argv:
        open_window()
    elif keep_open[0]:
        open_minimized()  # at login: start with the taskbar button (and its badge) ready
    menu = pystray.Menu(
        pystray.MenuItem("Open inbox", open_window, default=True),
        pystray.MenuItem("Mark all read", mark_all),
        pystray.MenuItem("Keep in taskbar", toggle_keep, checked=lambda item: keep_open[0]),
        pystray.MenuItem("Restart", lambda icon, *_: control("restart")),
        pystray.MenuItem("Quit", lambda icon, *_: control("quit")),
    )
    icon = pystray.Icon("agent-manager", with_badge(0), "Agent Manager", menu)
    inbox.ON_NOTIFY = icon.notify
    icon.run(setup=loop)
    STOP.set()
    if server["http"]:
        server["http"].shutdown()
        server["http"].server_close()
    if _mutex:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle(_mutex)
    if restart_requested[0]:
        subprocess.Popen([sys.executable, os.path.join(HERE, "tray.py"), "--open"],
                         creationflags=subprocess.CREATE_NO_WINDOW)
