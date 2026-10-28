"""Chat inbox tray app: runs the inbox server and a system-tray icon with an unread badge.
Left-click opens the inbox as a Chrome app window. Run with pythonw (no console)."""
import ctypes
import os
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer

import pystray
from PIL import Image, ImageDraw, ImageFont

import inbox
import taskbar

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = f"http://localhost:{inbox.PORT}"
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


keep_open = [True]


def toggle_keep(icon, item):
    keep_open[0] = not keep_open[0]


def open_window(*_):
    """Focus the existing inbox window, or start one. Never opens a second window."""
    hwnd = taskbar.find_window()
    if hwnd:
        taskbar.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        taskbar.user32.SetForegroundWindow(hwnd)
        return
    last_open[0] = time.time()
    subprocess.Popen([CHROME, f"--app={URL}", f"--user-data-dir={os.path.join(HERE, 'chrome_profile')}"])


def mark_all(icon, *_):
    inbox.unread_json(mark_all=True)
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
    return taskbar.find_window() is not None


def open_minimized():
    si = subprocess.STARTUPINFO()
    si.dwFlags = subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
    subprocess.Popen([CHROME, f"--app={URL}", f"--user-data-dir={os.path.join(HERE, 'chrome_profile')}"], startupinfo=si)


last_open = [0.0]
server = {"thread": None}


def start_server():
    """(Re)start the web server thread; harmless if the port is already served by another copy."""
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", inbox.PORT), inbox.H)
    except OSError:
        return
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    server["thread"] = t
    inbox.log("server started")


def refresh(icon):
    n = inbox.unread_count()
    icon.icon = with_badge(n)
    icon.title = f"Chat inbox: {n} unread" if n else "Chat inbox: all caught up"
    hwnd = taskbar.find_window()
    if hwnd is None:
        pass  # window closed on purpose: stay closed; the tray icon still carries the count
    else:
        taskbar.set_badge(hwnd, badge_only(n) if n else None, f"{n} unread")
        taskbar.brand_window(hwnd, CHROME, URL, os.path.join(HERE, "chrome_profile"), os.path.join(HERE, "inbox.ico"))


def loop(icon):
    icon.visible = True
    while icon.visible:
        try:
            t = server["thread"]
            if t is None or not t.is_alive():
                start_server()  # watchdog: the server must always be up
            refresh(icon)
        except Exception as e:  # never let the loop die
            inbox.log("tray loop error: " + repr(e))
        time.sleep(10)


def already_running():
    """Single instance: a named mutex, so Task Scheduler can relaunch freely without duplicates."""
    ctypes.windll.kernel32.CreateMutexW(None, False, "ChatInboxTrayMutex")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


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
    if "--open" in sys.argv:
        open_window()
    elif keep_open[0]:
        open_minimized()  # at login: start with the taskbar button (and its badge) ready
    menu = pystray.Menu(
        pystray.MenuItem("Open inbox", open_window, default=True),
        pystray.MenuItem("Mark all read", mark_all),
        pystray.MenuItem("Keep in taskbar", toggle_keep, checked=lambda item: keep_open[0]),
        pystray.MenuItem("Quit", lambda icon, *_: icon.stop()),
    )
    pystray.Icon("chat-inbox", with_badge(0), "Chat inbox", menu).run(setup=loop)
