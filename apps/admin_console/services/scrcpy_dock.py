# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Native Companion Hardware Dock Bar for Scrcpy Window.

Creates a sticky, stylish desktop floating navigation & shortcut toolbar
that docks tightly to the bottom of the active Scrcpy window:
- [◀ 返回] (Back)
- [● 主页] (Home)
- [■ 多任务] (App Switch)
- [🔔 通知] (Notifications)
- [⏻ 电源] (Power/Wake)
- [🔊+] [🔉-] (Volume)
- [📋 剪贴板直投] (Paste clipboard text into phone)
"""

import asyncio
import os
import subprocess
import sys
import threading
import time

try:
    import win32api
    import win32con
    import win32gui
except ImportError:
    win32gui = None


class ScrcpyCompanionDock:
    def __init__(self, serial: str | None = None, window_keyword: str = "Artemis"):
        self.serial = serial
        self.window_keyword = window_keyword
        self.target_hwnd = None
        self.dock_hwnd = None
        self.is_running = False
        self._thread = None

    def _find_target_window(self):
        found = []

        def enum_cb(hwnd, res):
            if win32gui.IsWindowVisible(hwnd):
                text = win32gui.GetWindowText(hwnd)
                if self.window_keyword in text:
                    res.append((hwnd, text))

        win32gui.EnumWindows(enum_cb, found)
        if found:
            return found[0][0]
        return None

    def _send_adb_key(self, keycode: str):
        try:
            cmd = ["adb"]
            if self.serial:
                cmd.extend(["-s", self.serial])
            cmd.extend(["shell", "input", "keyevent", keycode])
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _send_clipboard_to_phone(self):
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            if text:
                escaped = text.replace(" ", "%s").replace("\n", "").replace('"', '\\"')
                cmd = ["adb"]
                if self.serial:
                    cmd.extend(["-s", self.serial])
                cmd.extend(["shell", "input", "text", f'"{escaped}"'])
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def run_gui_loop(self):
        # Poll for target scrcpy window
        for _ in range(30):
            self.target_hwnd = self._find_target_window()
            if self.target_hwnd:
                break
            time.sleep(0.3)

        if not self.target_hwnd:
            return

        hInstance = win32api.GetModuleHandle(None)

        def wndProc(hwnd, msg, wParam, lParam):
            if msg == win32con.WM_COMMAND:
                bid = wParam & 0xFFFF
                if bid == 101:
                    self._send_adb_key("KEYCODE_BACK")
                elif bid == 102:
                    self._send_adb_key("KEYCODE_HOME")
                elif bid == 103:
                    self._send_adb_key("KEYCODE_APP_SWITCH")
                elif bid == 104:
                    self._send_adb_key("KEYCODE_NOTIFICATION")
                elif bid == 105:
                    self._send_adb_key("KEYCODE_POWER")
                elif bid == 106:
                    self._send_adb_key("KEYCODE_VOLUME_UP")
                elif bid == 107:
                    self._send_adb_key("KEYCODE_VOLUME_DOWN")
                elif bid == 108:
                    self._send_clipboard_to_phone()
            elif msg == win32con.WM_DESTROY:
                win32gui.PostQuitMessage(0)
                return 0
            return win32gui.DefWindowProc(hwnd, msg, wParam, lParam)

        className = "ArtemisScrcpyCompanionDock"
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = wndProc
        wc.lpszClassName = className
        wc.hInstance = hInstance
        wc.hbrBackground = win32gui.GetStockObject(win32con.LTGRAY_BRUSH)
        try:
            win32gui.RegisterClass(wc)
        except Exception:
            pass

        # Calculate initial position: docked to the RIGHT side of the scrcpy phone window
        rect = win32gui.GetWindowRect(self.target_hwnd)
        left, top, right, bottom = rect
        dock_w = 72
        dock_h = 8 * 38 + 10
        # Position vertically aligned to top of scrcpy window, placed at right edge
        x = right
        y = max(10, top + 30)

        self.dock_hwnd = win32gui.CreateWindowEx(
            win32con.WS_EX_TOPMOST | win32con.WS_EX_TOOLWINDOW,
            className,
            "Artemis 侧边实体按键栏",
            win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_BORDER,
            x, y, dock_w, dock_h,
            0, 0, hInstance, None
        )

        buttons = [
            ("◀ 返回", 101),
            ("● 桌面", 102),
            ("■ 任务", 103),
            ("🔔 通知", 104),
            ("⏻ 亮灭", 105),
            ("🔊 音量+", 106),
            ("🔉 音量-", 107),
            ("📋 粘贴", 108),
        ]

        for idx, (text, bid) in enumerate(buttons):
            by = 6 + idx * 37
            win32gui.CreateWindow(
                "BUTTON", text,
                win32con.WS_TABSTOP | win32con.WS_VISIBLE | win32con.WS_CHILD | win32con.BS_PUSHBUTTON,
                5, by, 60, 32,
                self.dock_hwnd, bid, hInstance, None
            )

        self.is_running = True

        # Watchdog loop: follow target window position and snap to RIGHT side
        def follower():
            while self.is_running:
                try:
                    if not win32gui.IsWindow(self.target_hwnd):
                        break
                    t_rect = win32gui.GetWindowRect(self.target_hwnd)
                    t_left, t_top, t_right, t_bottom = t_rect
                    # Snap vertically directly beside the right border of the scrcpy window
                    snap_x = t_right - 1
                    snap_y = max(10, t_top + 30)
                    win32gui.SetWindowPos(
                        self.dock_hwnd,
                        win32con.HWND_TOPMOST,
                        snap_x, snap_y, dock_w, dock_h,
                        win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
                    )
                    time.sleep(0.04)
                except Exception:
                    break
            if self.dock_hwnd and win32gui.IsWindow(self.dock_hwnd):
                win32gui.DestroyWindow(self.dock_hwnd)

        threading.Thread(target=follower, daemon=True).start()
        win32gui.PumpMessages()

    def start_in_background(self):
        self._thread = threading.Thread(target=self.run_gui_loop, daemon=True)
        self._thread.start()


def launch_companion_dock(serial: str | None = None, window_keyword: str = "Artemis"):
    dock = ScrcpyCompanionDock(serial=serial, window_keyword=window_keyword)
    dock.start_in_background()
    return dock


if __name__ == "__main__":
    import sys
    target_serial = sys.argv[1] if len(sys.argv) > 1 else None
    dock = ScrcpyCompanionDock(serial=target_serial)
    dock.run_gui_loop()
