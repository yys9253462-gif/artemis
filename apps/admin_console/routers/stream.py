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

"""Device Screen Live Streaming & Interactive Virtual Touch Control Router.

Exposes real-time screen streaming and bidirectional user touch injection endpoints.
"""

import asyncio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

try:
    from admin_console.services.device_stream_service import device_stream_service
    from admin_console.services.wifi_adb_service import wifi_adb_service
except ImportError:
    from apps.admin_console.services.device_stream_service import device_stream_service
    from apps.admin_console.services.wifi_adb_service import wifi_adb_service

router = APIRouter(tags=["stream"])


@router.get("/api/stream/device-live")
async def stream_device_live(device: str | None = None):
    """Streams live device screen frames as multipart MJPEG for a specified or default device."""
    return StreamingResponse(
        device_stream_service.mjpeg_frame_generator(serial=device),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/stream/devices-state")
async def get_all_devices_stream_state():
    """Returns all connected devices and their corresponding live stream endpoints."""
    serials = await device_stream_service.get_connected_devices()
    devices_info = [
        {
            "serial": s,
            "connected": True,
            "live_stream_url": f"/api/stream/device-live?device={s}",
        }
        for s in serials
    ]
    return JSONResponse({
        "total": len(serials),
        "devices": devices_info,
        "primary_serial": serials[0] if serials else None
    })


@router.get("/api/stream/device-state")
async def get_device_stream_state():
    """Returns whether an ADB device is connected and live streaming is available."""
    serial = await device_stream_service.get_device_serial()
    return JSONResponse(
        {
            "connected": serial is not None,
            "serial": serial,
            "live_stream_url": "/api/stream/device-live" if serial else None,
        }
    )


@router.post("/api/stream/touch")
async def inject_device_touch(request: Request):
    """Inject interactive user touch inputs (tap, swipe, keyevent, text) to real phone(s).
    Supports target device serial or sync=True for dual/multi-device synchronized touch!
    """
    payload = await request.json()
    action = payload.get("action", "tap")
    target_device = payload.get("device")
    success = await device_stream_service.inject_touch_event(action, payload, target_serial=target_device)
    return JSONResponse({"success": success, "action": action, "device": target_device})


@router.post("/api/stream/launch-scrcpy")
async def launch_native_scrcpy(request: Request):
    """Launch hardware-accelerated, ultra-low latency (<30ms) 60fps Scrcpy desktop window with companion hardware dock bar."""
    from artemis.toolchain import find_scrcpy
    from apps.admin_console.services.scrcpy_dock import launch_companion_dock

    try:
        body = await request.json()
    except Exception:
        body = {}

    target_serial = body.get("device") or await device_stream_service.get_device_serial()
    scrcpy_bin = find_scrcpy()
    cmd = [scrcpy_bin]
    if target_serial:
        cmd.extend(["-s", target_serial])
    
    title_serial = f" - {target_serial}" if target_serial else ""
    cmd.extend([
        f"--window-title=Artemis 极速真机操控 (60fps 零延迟){title_serial}",
        "-m", "1080",
        "--max-fps", "60",
        "--always-on-top",
        "--keyboard=uhid",  # 模拟物理键盘，电脑输入法打字直接无缝输入到手机！
    ])
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        # Launch the companion physical dock bar attached right below the scrcpy window
        launch_companion_dock(serial=target_serial, window_keyword="Artemis")
        return JSONResponse({"success": True, "pid": proc.pid, "device": target_serial, "message": "Scrcpy 极速窗口与实体导航控制栏已开启"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Wireless ADB Management Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/wifi-adb/devices")
async def list_wifi_adb_devices():
    """List connected devices and wireless status."""
    devices = await wifi_adb_service.get_connected_devices()
    return JSONResponse({"devices": devices})


@router.post("/api/wifi-adb/connect")
async def connect_wifi_adb(request: Request):
    """Connect to a Wi-Fi device by IP:Port."""
    body = await request.json()
    address = body.get("address", "")
    res = await wifi_adb_service.connect_device(address)
    return JSONResponse(res)


@router.post("/api/wifi-adb/pair")
async def pair_wifi_adb(request: Request):
    """Pair an Android 11+ wireless debugging phone and auto-connect."""
    body = await request.json()
    address = body.get("address", "")
    code = body.get("code", "")
    connect_port = body.get("connect_port")
    res = await wifi_adb_service.pair_device(address, code, connect_port=connect_port)
    return JSONResponse(res)


@router.post("/api/wifi-adb/scan-and-connect")
async def scan_and_connect_wifi_adb():
    """Auto scan local mDNS and subnet port 5555 to automatically connect wireless phones."""
    res = await wifi_adb_service.auto_discover_and_connect()
    return JSONResponse(res)
