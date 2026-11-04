"""Taskbar badge: finds the inbox's Chrome app window and sets a Windows overlay icon (the number) on its taskbar button."""
import ctypes
import os
import sys
import tempfile
import re
import threading
from ctypes import wintypes

user32 = ctypes.windll.user32
ole32 = ctypes.windll.ole32
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HICON
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = wintypes.LPARAM

CLSID_TaskbarList = (ctypes.c_ubyte * 16).from_buffer_copy(
    bytes.fromhex("44F3FD56" "6DFD" "d011" "958A006097C9A090"))
IID_ITaskbarList3 = (ctypes.c_ubyte * 16).from_buffer_copy(
    bytes.fromhex("91FB1AEA" "289E" "864B" "90E99E9F8A5EEFAF"))

_thread = threading.local()


def _taskbar():
    if not hasattr(_thread, "tb"):
        ole32.CoInitialize(None)
        pointer = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(CLSID_TaskbarList), None, 1, ctypes.byref(IID_ITaskbarList3), ctypes.byref(pointer))
        _thread.tb = pointer if hr == 0 else None
        if _thread.tb:
            vt = ctypes.cast(ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
            ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vt[3])(pointer)
    return _thread.tb


def _call(index, restype, argtypes, *args):
    pointer = _taskbar()
    if not pointer:
        return None
    vt = ctypes.cast(ctypes.cast(pointer, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vt[index])
    return fn(pointer, *args)


def find_windows(title_part=None):
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        if cls.value == "Chrome_WidgetWin_1" and (user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd)):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if (title_part and title_part in buf.value) or (not title_part and re.fullmatch(r"(?:\(\d+\) )?(?:Agent Manager|Chat inbox)", buf.value)):
                found.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return found


def find_window(title_part=None):
    found = find_windows(title_part)
    return found[0] if found else None


def close_extra_windows(title_part=None):
    """Keep one inbox window; Chrome may restore a saved copy next to the one we launch."""
    for hwnd in find_windows(title_part)[1:]:
        user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE


def set_badge(hwnd, image, label):
    """image: PIL RGBA image or None to clear."""
    if not _taskbar() or not hwnd:
        return
    hicon = None
    if image is not None:
        path = os.path.join(tempfile.gettempdir(), "chat_inbox_badge.ico")
        image.save(path, format="ICO", sizes=[(32, 32)])
        hicon = user32.LoadImageW(None, path, 1, 32, 32, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
    _call(18, ctypes.c_long, [wintypes.HWND, wintypes.HICON, wintypes.LPCWSTR], hwnd, hicon, label)
    if hicon:
        user32.DestroyIcon(hicon)


# ---- window identity: our own icon, name and relaunch command so pinning keeps the logo instead of Chrome's ----
class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("a", ctypes.c_ushort), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort),
                ("p", ctypes.c_void_p), ("q", ctypes.c_void_p)]


class PKEY(ctypes.Structure):
    _fields_ = [("guid", ctypes.c_ubyte * 16), ("pid", ctypes.c_ulong)]


_IID_PROPSTORE = (ctypes.c_ubyte * 16).from_buffer_copy(bytes.fromhex("EB8E6D88" "F28C" "4644" "8D02CDBA1DBDCF99"))
_APPMODEL = bytes.fromhex("55284C9F" "799F" "394B" "A8D0E1D42DE1D5F3")
_keep = []
_branded = {}


def _set_str(store, pid, text):
    buf = ctypes.create_unicode_buffer(text)
    _keep.append(buf)
    pv = PROPVARIANT(31, 0, 0, 0, ctypes.cast(buf, ctypes.c_void_p).value, 0)  # VT_LPWSTR
    key = PKEY((ctypes.c_ubyte * 16).from_buffer_copy(_APPMODEL), pid)
    fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(PKEY), ctypes.POINTER(PROPVARIANT))
    vt = ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    return fn(vt[6])(store, ctypes.byref(key), ctypes.byref(pv))  # IPropertyStore::SetValue


def brand_window(hwnd, chrome, url, profile, ico):
    """Give the window our icon (WM_SETICON) and AppUserModel properties. Done once per window handle."""
    if not hwnd or _branded.get(hwnd):
        return
    _taskbar()  # initialize COM on the thread that owns the property-store calls
    for size, which in ((32, 1), (16, 0)):
        h = user32.LoadImageW(None, ico, 1, size, size, 0x10)
        if h:
            user32.SendMessageW(hwnd, 0x80, which, h)  # WM_SETICON big/small
    store = ctypes.c_void_p()
    hr = ctypes.windll.shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(_IID_PROPSTORE), ctypes.byref(store))
    if hr == 0 and store:
        pythonw = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "pythonw.exe")
        cmd = f'"{pythonw}" "{os.path.join(os.path.dirname(os.path.abspath(__file__)), "tray.py")}" --open'
        _set_str(store, 5, "ChatInbox.App")
        _set_str(store, 2, cmd)
        _set_str(store, 3, ico + ",0")
        _set_str(store, 4, "Agent Manager")
        commit = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(
            ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))[7])
        commit(store)
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
            ctypes.cast(ctypes.cast(store, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))[2])
        release(store)
    _branded[hwnd] = True
