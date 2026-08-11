"""Tests for the taskbar flash notification (ctypes.windll.user32.FlashWindowEx).

Windows-only, like the module under test — this project only ships on
Windows, so there is no cross-platform skip here.
"""
from unittest.mock import patch

from tokengotchi.renderer.taskbar_flash import (
    FLASHW_TIMERNOFG,
    FLASHW_TRAY,
    flash_taskbar,
)

_MOD = "tokengotchi.renderer.taskbar_flash"


def test_no_window_handle_skips_flash():
    with patch(f"{_MOD}.pygame.display.get_wm_info", return_value={}), \
         patch(f"{_MOD}.ctypes.windll.user32.GetForegroundWindow") as mock_fg, \
         patch(f"{_MOD}.ctypes.windll.user32.FlashWindowEx") as mock_flash:
        flash_taskbar()

    mock_flash.assert_not_called()
    mock_fg.assert_not_called()


def test_already_foreground_skips_flash():
    hwnd = 12345
    with patch(f"{_MOD}.pygame.display.get_wm_info", return_value={'window': hwnd}), \
         patch(f"{_MOD}.ctypes.windll.user32.GetForegroundWindow", return_value=hwnd), \
         patch(f"{_MOD}.ctypes.windll.user32.FlashWindowEx") as mock_flash:
        flash_taskbar()

    mock_flash.assert_not_called()


def test_background_window_flashes_with_correct_flags():
    hwnd = 12345
    with patch(f"{_MOD}.pygame.display.get_wm_info", return_value={'window': hwnd}), \
         patch(f"{_MOD}.ctypes.windll.user32.GetForegroundWindow", return_value=99999), \
         patch(f"{_MOD}.ctypes.windll.user32.FlashWindowEx") as mock_flash:
        flash_taskbar()

    mock_flash.assert_called_once()
    (arg,), _ = mock_flash.call_args
    info = arg._obj if hasattr(arg, "_obj") else arg
    assert info.dwFlags == (FLASHW_TRAY | FLASHW_TIMERNOFG) == 0xE
    assert info.hwnd == hwnd
    assert info.uCount == 0
    assert info.dwTimeout == 0


def test_flash_window_ex_raising_does_not_propagate():
    hwnd = 12345
    with patch(f"{_MOD}.pygame.display.get_wm_info", return_value={'window': hwnd}), \
         patch(f"{_MOD}.ctypes.windll.user32.GetForegroundWindow", return_value=99999), \
         patch(f"{_MOD}.ctypes.windll.user32.FlashWindowEx", side_effect=OSError("boom")):
        flash_taskbar()  # must not raise
