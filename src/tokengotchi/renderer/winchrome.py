"""Win32 window-chrome helpers — frameless rounded case, drag, minimize.

Everything here manipulates the OS window that SDL created: it makes the process
DPI-aware, clips the window to a rounded rectangle so the case corners show the
desktop, moves the window during a drag, minimizes it, and clamps a proposed
position onto the visible work area.

Like `taskbar_flash`, this is Windows-only and NON-CRITICAL: every OS call is
wrapped so any failure (non-Windows platform, missing HWND, rejected ctypes
call) degrades to a silent no-op and never raises. The one exception is
`clamp_to_workarea`, which is pure arithmetic with a safe fallback and is unit
tested directly.

DPI awareness must be set BEFORE `pygame.init()` / `set_mode`, or the rounded
region (in physical pixels) and the painted case edge drift apart on a scaled
monitor and both get bitmap-stretched. Everything else is called after the
window exists.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

import pygame

# Case geometry: the painted body is inset BEZEL=8 from the window edge at corner
# radius 22, so the outermost case edge rounds at 8 + 22 = 30. The window region
# clips the full window at this radius so the dark backing plate becomes a rim
# concentric with the body.
ROUND_RADIUS = 30

# GetSystemMetrics indices for the virtual screen (all monitors), used only as a
# fallback bound; the primary clamp target is the work area of the monitor the
# window sits on.
_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79

_GWL_STYLE = -16
_WS_SYSMENU = 0x00080000

_MONITOR_DEFAULTTONEAREST = 2


def set_dpi_aware() -> None:
    """Make the process per-monitor DPI aware. Call BEFORE pygame.init().

    Without this, a scaled monitor (125/150%) makes DWM bitmap-stretch the
    whole window: the case blurs and the rounded region clip shifts off the
    painted edge. Tries the modern per-monitor-v2 API first, then older ones.
    """
    try:
        # PER_MONITOR_AWARE_V2 = -4, passed as a context handle.
        ctypes.windll.user32.SetProcessDpiAwarenessContext(
            ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2 (Win 8.1+).
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        return


def _hwnd():
    """The OS window handle SDL created, or None off-Windows / pre-display."""
    try:
        return pygame.display.get_wm_info().get('window')
    except Exception:
        return None


def apply_round_region(width: int, height: int,
                       radius: int = ROUND_RADIUS) -> None:
    """Clip the window to a rounded rect so the case corners show the desktop.

    Uses a 1-bit region (hard-edged, not antialiased); at radius 30 the corner
    curve reads clean at normal viewing distance. The window takes ownership of
    the region handle, so it must NOT be deleted here. Survives
    minimize/restore/move; only needs re-applying if set_mode is called again.
    """
    try:
        hwnd = _hwnd()
        if not hwnd:
            return
        gdi = ctypes.windll.gdi32
        user = ctypes.windll.user32
        gdi.CreateRoundRectRgn.restype = wintypes.HRGN
        gdi.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        user.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN,
                                      wintypes.BOOL]
        # GDI right/bottom are exclusive, so +1; ellipse size is 2*radius.
        rgn = gdi.CreateRoundRectRgn(0, 0, width + 1, height + 1,
                                     radius * 2, radius * 2)
        user.SetWindowRgn(hwnd, rgn, True)
    except Exception:
        return


def restore_sysmenu() -> None:
    """Re-add WS_SYSMENU so Alt+Space -> Move survives as an OS recovery path.

    A NOFRAME window drops WS_SYSMENU, removing the last OS way to reposition a
    window dragged off-screen. Re-adding it is a cheap backstop behind the
    drag-clamp; it does not bring back the visible title bar.
    """
    try:
        hwnd = _hwnd()
        if not hwnd:
            return
        user = ctypes.windll.user32
        try:
            get_style = user.GetWindowLongPtrW
            set_style = user.SetWindowLongPtrW
        except AttributeError:
            get_style = user.GetWindowLongW
            set_style = user.SetWindowLongW
        style = get_style(hwnd, _GWL_STYLE)
        set_style(hwnd, _GWL_STYLE, style | _WS_SYSMENU)
    except Exception:
        return


def minimize() -> None:
    """Minimize the window to the taskbar (recoverable — taskbar button stays)."""
    try:
        hwnd = _hwnd()
        if not hwnd:
            return
        # SW_MINIMIZE = 6.
        ctypes.windll.user32.ShowWindow(hwnd, 6)
    except Exception:
        return


def global_cursor() -> tuple[int, int] | None:
    """Screen-global cursor position, or None on failure.

    Global (not window-relative) so drag math stays in one coordinate space as
    the window moves under the cursor.
    """
    try:
        pt = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return int(pt.x), int(pt.y)
    except Exception:
        pass
    return None


def window_origin() -> tuple[int, int] | None:
    """Top-left of the window in screen coordinates, or None."""
    try:
        hwnd = _hwnd()
        if not hwnd:
            return None
        rect = wintypes.RECT()
        if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return int(rect.left), int(rect.top)
    except Exception:
        pass
    return None


def move_window(x: int, y: int) -> None:
    """Move the window's top-left to (x, y) in screen coordinates."""
    try:
        hwnd = _hwnd()
        if not hwnd:
            return
        # SWP_NOSIZE=1 | SWP_NOZORDER=4 | SWP_NOACTIVATE=0x10.
        ctypes.windll.user32.SetWindowPos(hwnd, 0, int(x), int(y), 0, 0,
                                          1 | 4 | 0x10)
    except Exception:
        return


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _work_area(cursor: tuple[int, int] | None = None
               ) -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) work area of the monitor under the CURSOR.

    Resolving the monitor from the cursor point — not the window — is what lets
    a drag cross monitors: during a drag the cursor is always on a real monitor
    (the OS forbids it entering the dead zones a multi-monitor bounding box can
    contain), so the clamp target follows the cursor across boundaries and the
    grab strip is always dropped somewhere reachable. Resolving from the window
    instead pins it to whatever monitor it started on — the "dragged down but
    can't drag back up" bug. Work area excludes the taskbar. None on failure.
    """
    try:
        user = ctypes.windll.user32
        if cursor is not None:
            pt = wintypes.POINT(int(cursor[0]), int(cursor[1]))
            mon = user.MonitorFromPoint(pt, _MONITOR_DEFAULTTONEAREST)
        else:
            hwnd = _hwnd()
            mon = (user.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
                   if hwnd else None)
        if mon:
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if user.GetMonitorInfoW(mon, ctypes.byref(mi)):
                r = mi.rcWork
                return int(r.left), int(r.top), int(r.right), int(r.bottom)
    except Exception:
        pass
    return None


def clamp_to_workarea(x: int, y: int, win_w: int, win_h: int,
                      bounds: tuple[int, int, int, int],
                      handle_h: int = 40) -> tuple[int, int]:
    """Clamp a proposed window origin so the top control strip stays visible.

    ``bounds`` is (left, top, right, bottom) of the work area — which on a
    multi-monitor setup can have NEGATIVE coordinates, so this must never assume
    a (0, 0) origin. The window may hang off the bottom/right, but the top
    ``handle_h`` px (holding minimize/close and enough grab area) is kept fully
    on-screen so the window can always be dragged back.

    Pure arithmetic, no OS calls — unit tested directly.
    """
    left, top, right, bottom = bounds
    # Horizontal: keep the whole width on-screen when it fits; otherwise pin the
    # left edge to the work-area left so the controls (top-right) stay reachable.
    max_x = right - win_w
    if max_x < left:
        max_x = left
    x = max(left, min(x, max_x))
    # Vertical: the top edge may never go above the work area (that would push
    # the control strip off the top), and the handle strip must stay below the
    # bottom edge.
    max_y = bottom - handle_h
    if max_y < top:
        max_y = top
    y = max(top, min(y, max_y))
    return x, y


def clamp_window(x: int, y: int, win_w: int, win_h: int,
                 handle_h: int = 40,
                 cursor: tuple[int, int] | None = None) -> tuple[int, int]:
    """clamp_to_workarea against the work area of the monitor under ``cursor``
    (virtual-screen fallback). Passing the live cursor is what allows a drag to
    cross monitors — see `_work_area`. Returns the input unchanged if no bounds
    can be read."""
    bounds = _work_area(cursor)
    if bounds is None:
        try:
            gsm = ctypes.windll.user32.GetSystemMetrics
            vx = gsm(_SM_XVIRTUALSCREEN)
            vy = gsm(_SM_YVIRTUALSCREEN)
            vw = gsm(_SM_CXVIRTUALSCREEN)
            vh = gsm(_SM_CYVIRTUALSCREEN)
            bounds = (vx, vy, vx + vw, vy + vh)
        except Exception:
            return x, y
    return clamp_to_workarea(x, y, win_w, win_h, bounds, handle_h)
