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

"""Device Live Screen Streaming & Multi-Device Touch Injection Service.

Provides real-time, low-latency device screen frames over HTTP MJPEG and WebSocket.
Full support for multi-device concurrent streaming and synchronized touch injection.
"""

import asyncio
import io
import logging
import subprocess
import time
from collections.abc import AsyncGenerator
from PIL import Image

from artemis.toolchain import find_adb

logger = logging.getLogger("artemis.stream_service")


class SingleDeviceCapture:
    """Manages continuous background frame capture for a single serial."""

    def __init__(self, serial: str):
        self.serial = serial
        self._active_listeners = 0
        self._lock = asyncio.Lock()
        self._latest_frame: bytes | None = None
        self._last_frame_time: float = 0.0
        self._is_capturing = False
        self._capture_task: asyncio.Task | None = None

    async def _capture_loop(self):
        adb_bin = find_adb()
        while self._active_listeners > 0:
            try:
                start_t = time.time()
                cmd = [adb_bin, "-s", self.serial, "exec-out", "screencap", "-p"]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0 and len(stdout) > 1000:
                    png_idx = stdout.find(b"\x89PNG\r\n\x1a\n")
                    if png_idx != -1:
                        clean_png = stdout[png_idx:]
                        try:
                            img = Image.open(io.BytesIO(clean_png)).convert("RGB")
                            w, h = img.size
                            target_w = 480
                            target_h = int(h * (target_w / w))
                            img_small = img.resize((target_w, target_h), Image.Resampling.BILINEAR)
                            buf = io.BytesIO()
                            img_small.save(buf, format="JPEG", quality=75)
                            self._latest_frame = buf.getvalue()
                            self._last_frame_time = time.time()
                        except Exception as dec_err:
                            logger.debug(f"[StreamService:{self.serial}] Decode error: {dec_err}")
                            self._latest_frame = clean_png
                            self._last_frame_time = time.time()

                elapsed = time.time() - start_t
                delay = max(0.02, 0.06 - elapsed)
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[StreamService:{self.serial}] Capture error: {e}")
                await asyncio.sleep(0.5)

        self._is_capturing = False

    async def start_capturing(self):
        async with self._lock:
            self._active_listeners += 1
            if not self._is_capturing or self._capture_task is None or self._capture_task.done():
                self._is_capturing = True
                self._capture_task = asyncio.create_task(self._capture_loop())

    async def stop_capturing(self):
        async with self._lock:
            self._active_listeners = max(0, self._active_listeners - 1)
            if self._active_listeners == 0 and self._capture_task and not self._capture_task.done():
                self._capture_task.cancel()
                self._is_capturing = False

    async def mjpeg_generator(self) -> AsyncGenerator[bytes, None]:
        await self.start_capturing()
        try:
            last_sent_time = 0.0
            while True:
                if self._latest_frame and self._last_frame_time > last_sent_time:
                    last_sent_time = self._last_frame_time
                    frame_bytes = self._latest_frame
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: "
                        + str(len(frame_bytes)).encode()
                        + b"\r\n\r\n"
                        + frame_bytes
                        + b"\r\n"
                    )
                await asyncio.sleep(0.04)
        finally:
            await self.stop_capturing()


class DeviceStreamService:
    """Manages multi-device screen capture and synchronized touch injection."""

    def __init__(self):
        self._captures: dict[str, SingleDeviceCapture] = {}
        self._lock = asyncio.Lock()

    async def get_connected_devices(self) -> list[str]:
        """List all active online ADB device serials."""
        serials = []
        try:
            adb_bin = find_adb()
            proc = await asyncio.create_subprocess_exec(
                adb_bin,
                "devices",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            lines = stdout.decode().strip().splitlines()
            for line in lines[1:]:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1] == "device":
                    serials.append(parts[0])
        except Exception as e:
            logger.warning(f"Error checking adb devices: {e}")
        return serials

    async def get_device_serial(self) -> str | None:
        """Get the primary active ADB device serial."""
        devices = await self.get_connected_devices()
        return devices[0] if devices else None

    async def _get_or_create_capture(self, serial: str | None = None) -> SingleDeviceCapture | None:
        async with self._lock:
            if not serial:
                serial = await self.get_device_serial()
            if not serial:
                return None
            if serial not in self._captures:
                self._captures[serial] = SingleDeviceCapture(serial)
            return self._captures[serial]

    async def mjpeg_frame_generator(self, serial: str | None = None) -> AsyncGenerator[bytes, None]:
        """Async generator streaming MJPEG multipart bytes for a specific device or default device."""
        capture = await self._get_or_create_capture(serial)
        if not capture:
            # Empty stream when no device connected
            yield (
                b"--frame\r\n"
                b"Content-Type: text/plain\r\n\r\n"
                b"No device connected\r\n"
            )
            return
        async for chunk in capture.mjpeg_generator():
            yield chunk

    async def inject_touch_event(self, action: str, data: dict, target_serial: str | None = None) -> bool:
        """Inject virtual touch events (tap, swipe, keyevent, text) directly to device(s)."""
        # If target_serial is "all" or sync=True, inject to all connected devices simultaneously
        sync_all = data.get("sync", False) or target_serial == "all"
        serials = []
        if sync_all:
            serials = await self.get_connected_devices()
        elif target_serial:
            serials = [target_serial]
        else:
            primary = await self.get_device_serial()
            if primary:
                serials = [primary]

        if not serials:
            return False

        adb_bin = find_adb()
        success = True

        for s in serials:
            prefix = [adb_bin, "-s", s, "shell", "input"]
            try:
                if action == "tap":
                    x = int(data.get("x", 0))
                    y = int(data.get("y", 0))
                    proc = await asyncio.create_subprocess_exec(*prefix, "tap", str(x), str(y))
                    await proc.communicate()
                    success = success and (proc.returncode == 0)

                elif action == "swipe":
                    x1 = int(data.get("x1", 0))
                    y1 = int(data.get("y1", 0))
                    x2 = int(data.get("x2", 0))
                    y2 = int(data.get("y2", 0))
                    duration = int(data.get("duration", 300))
                    proc = await asyncio.create_subprocess_exec(*prefix, "swipe", str(x1), str(y1), str(x2), str(y2), str(duration))
                    await proc.communicate()
                    success = success and (proc.returncode == 0)

                elif action == "keyevent":
                    keycode = data.get("keycode", "KEYCODE_BACK")
                    proc = await asyncio.create_subprocess_exec(*prefix, "keyevent", str(keycode))
                    await proc.communicate()
                    success = success and (proc.returncode == 0)

                elif action == "text":
                    text = str(data.get("text", ""))
                    escaped = text.replace(" ", "%s")
                    proc = await asyncio.create_subprocess_exec(*prefix, "text", escaped)
                    await proc.communicate()
                    success = success and (proc.returncode == 0)
            except Exception as e:
                logger.error(f"[StreamService] Touch event failed on {s} ({action}): {e}")
                success = False

        return success


device_stream_service = DeviceStreamService()
