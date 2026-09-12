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
async def stream_device_live():
    """Streams live device screen frames as multipart MJPEG."""
    return StreamingResponse(
        device_stream_service.mjpeg_frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive",
        },
    )


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
    """Inject interactive user touch inputs (tap, swipe, keyevent, text) to real phone."""
    payload = await request.json()
    action = payload.get("action", "tap")
    success = await device_stream_service.inject_touch_event(action, payload)
    return JSONResponse({"success": success, "action": action})


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
    """Pair an Android 11+ wireless debugging phone."""
    body = await request.json()
    address = body.get("address", "")
    code = body.get("code", "")
    res = await wifi_adb_service.pair_device(address, code)
    return JSONResponse(res)


@router.post("/api/wifi-adb/scan-and-connect")
async def scan_and_connect_wifi_adb():
    """Auto scan local mDNS and subnet port 5555 to automatically connect wireless phones."""
    res = await wifi_adb_service.auto_discover_and_connect()
    return JSONResponse(res)
