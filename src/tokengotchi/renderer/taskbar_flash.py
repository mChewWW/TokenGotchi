"""Taskbar flash notification — pure stdlib, Windows only.

Flashes the app's taskbar entry via `FlashWindowEx` so a dialogue line that
appears while the window is unfocused isn't easily missed. Deliberately
flash-only, not a full OS toast: no AppUserModelID or registered shortcut is
needed, and no third-party dependency (`pywin32`, `winotify`) is pulled in.

`FLASHW_TIMERNOFG` means Windows itself stops the flash the instant the
window regains foreground — there is no manual stop-flashing call, and no
risk of a flash running forever unattended.

This is a decoration feature, not a critical path: any failure (non-Windows
platform, unusual video driver, pygame not yet initialized with a display,
ctypes call rejected) must degrade to a silent no-op, never raise.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes

import pygame

FLASHW_TRAY = 0x2
FLASHW_TIMERNOFG = 0xC


class _FLASHWINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("hwnd", ctypes.wintypes.HWND),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("uCount", ctypes.wintypes.UINT),
        ("dwTimeout", ctypes.wintypes.DWORD),
    ]


def flash_taskbar() -> None:
    """Flash the app's taskbar entry, unless it's already the foreground window.

    Silently does nothing on any failure — missing HWND, non-Windows
    platform, or a rejected ctypes call.
    """
    try:
        hwnd = pygame.display.get_wm_info().get('window')
        if not hwnd:
            return

        if ctypes.windll.user32.GetForegroundWindow() == hwnd:
            return

        info = _FLASHWINFO()
        info.cbSize = ctypes.sizeof(_FLASHWINFO)
        info.hwnd = hwnd
        info.dwFlags = FLASHW_TRAY | FLASHW_TIMERNOFG
        info.uCount = 0
        info.dwTimeout = 0
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        return
