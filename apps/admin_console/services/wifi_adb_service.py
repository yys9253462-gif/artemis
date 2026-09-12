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

"""Wireless Wi-Fi ADB Auto-Scanner & Watchdog Service.

Features:
1. Auto mDNS wireless discovery (adb mdns services).
2. Subnet scanner for common wireless debugging ports (5555, 30000-45000).
3. Background connection health-check & auto-reconnect watchdog loop.
4. One-click manual pair / connect endpoint support.
"""

import asyncio
import logging
import re
import subprocess
import socket
from typing import Any
from artemis.toolchain import find_adb

logger = logging.getLogger("artemis.wifi_adb_service")


class WifiAdbService:
    """Manages wireless ADB scanning, pairing, and reconnect watchdog."""

    def __init__(self):
        self._watchdog_task: asyncio.Task | None = None
        self._is_running = False
        self._known_endpoints: set[str] = set()
        self._scanning = False

    async def run_adb_cmd(self, *args: str) -> tuple[int, str, str]:
        """Execute adb command asynchronously and return code, stdout, stderr."""
        try:
            adb_bin = find_adb()
            proc = await asyncio.create_subprocess_exec(
                adb_bin,
                *args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode or 0, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to execute adb {args}: {e}")
            return -1, "", str(e)

    async def get_connected_devices(self) -> list[dict[str, str]]:
        """List currently attached ADB devices with serial and connection state."""
        _, stdout, _ = await self.run_adb_cmd("devices", "-l")
        devices = []
        for line in stdout.strip().splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1]
                is_wifi = ":" in serial
                devices.append({
                    "serial": serial,
                    "state": state,
                    "is_wifi": is_wifi,
                    "info": line
                })
        return devices

    async def connect_device(self, address: str) -> dict[str, Any]:
        """Connect to a Wi-Fi device by IP:Port."""
        address = address.strip()
        if not address:
            return {"success": False, "message": "Address cannot be empty."}
        
        if ":" not in address:
            address = f"{address}:5555"

        code, stdout, stderr = await self.run_adb_cmd("connect", address)
        output = (stdout + stderr).strip()
        success = "connected to" in output.lower()
        if success:
            self._known_endpoints.add(address)
            logger.info(f"[WifiAdb] Successfully connected to {address}")
        return {
            "success": success,
            "address": address,
            "output": output
        }

    async def pair_device(self, address: str, pairing_code: str, connect_port: str | None = None) -> dict[str, Any]:
        """Pair an Android 11+ wireless debugging device using IP:Port and Pairing Code, then auto-connect."""
        address = address.strip()
        pairing_code = pairing_code.strip()
        if not address or not pairing_code:
            return {"success": False, "message": "Address and pairing code are required."}

        code, stdout, stderr = await self.run_adb_cmd("pair", address, pairing_code)
        output = (stdout + stderr).strip()
        success = "successfully paired" in output.lower()

        connect_msg = ""
        connect_success = False

        if success:
            # If user provided connection port (or default to pair port or 5555)
            host_ip = address.split(":")[0]
            target_connect_endpoint = f"{host_ip}:{connect_port}" if connect_port else (f"{host_ip}:5555")
            
            # If connect_port wasn't explicit, check mDNS first for the newly paired device connect port
            if not connect_port:
                await asyncio.sleep(1.0)
                mdns_list = await self.scan_mdns_services()
                for item in mdns_list:
                    ep = item.get("endpoint", "")
                    if ep.startswith(host_ip + ":"):
                        target_connect_endpoint = ep
                        break

            # Automatically connect to target endpoint
            conn_res = await self.connect_device(target_connect_endpoint)
            connect_success = conn_res.get("success", False)
            connect_msg = conn_res.get("output", "")

        return {
            "success": success,
            "address": address,
            "output": output,
            "connect_success": connect_success,
            "connect_message": connect_msg
        }

    async def scan_mdns_services(self) -> list[dict[str, Any]]:
        """Discover wireless debugging devices broadcasted over mDNS."""
        discovered = []
        _, stdout, _ = await self.run_adb_cmd("mdns", "services")
        for line in stdout.splitlines():
            line = line.strip()
            if not line or "List of discovered" in line:
                continue
            # Format usually: <instance_name> <service_type> <ip:port>
            parts = line.split()
            for part in parts:
                if ":" in part and re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$", part):
                    discovered.append({
                        "name": parts[0] if len(parts) > 1 else "Unknown Device",
                        "endpoint": part,
                        "raw": line
                    })
        return discovered

    def _get_local_subnet_base(self) -> str | None:
        """Find local host IPv4 subnet base (e.g. 192.168.5)."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            parts = ip.split(".")
            if len(parts) == 4:
                return ".".join(parts[:3])
        except Exception:
            pass
        return "192.168.5"

    async def scan_subnet(self, subnet_base: str | None = None, port: int = 5555, timeout: float = 0.25) -> list[str]:
        """Fast parallel probing for devices listening on ADB Wi-Fi port."""
        if self._scanning:
            return []
        self._scanning = True
        base = subnet_base or self._get_local_subnet_base() or "192.168.1"
        found_ips = []

        async def probe_ip(host: str):
            loop = asyncio.get_running_loop()
            try:
                def check():
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(timeout)
                        return s.connect_ex((host, port)) == 0
                is_open = await loop.run_in_executor(None, check)
                if is_open:
                    found_ips.append(f"{host}:{port}")
            except Exception:
                pass

        try:
            tasks = [probe_ip(f"{base}.{i}") for i in range(1, 255)]
            await asyncio.gather(*tasks)
        finally:
            self._scanning = False

        return found_ips

    async def auto_discover_and_connect(self) -> dict[str, Any]:
        """Perform unified scan (mDNS + subnet) and automatically connect reachable devices."""
        results = []
        # 1. mDNS discovery
        mdns_devices = await self.scan_mdns_services()
        for item in mdns_devices:
            endpoint = item["endpoint"]
            res = await self.connect_device(endpoint)
            results.append({"type": "mdns", "endpoint": endpoint, "result": res})

        # 2. If nothing discovered via mDNS, run subnet scan on port 5555
        if not results:
            subnet_endpoints = await self.scan_subnet(port=5555)
            for ep in subnet_endpoints:
                res = await self.connect_device(ep)
                results.append({"type": "subnet_5555", "endpoint": ep, "result": res})

        # Refresh device list
        active_devices = await self.get_connected_devices()
        return {
            "attempts": results,
            "connected_devices": active_devices
        }

    async def _watchdog_loop(self):
        """Background health check: periodically reconnects known Wi-Fi endpoints if disconnected."""
        logger.info("[WifiAdb] Watchdog loop started.")
        while self._is_running:
            try:
                await asyncio.sleep(15)
                devices = await self.get_connected_devices()
                online_serials = {d["serial"] for d in devices if d["state"] == "device"}
                
                for endpoint in list(self._known_endpoints):
                    if endpoint not in online_serials:
                        logger.info(f"[WifiAdb Watchdog] Reconnecting offline device: {endpoint}")
                        await self.connect_device(endpoint)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[WifiAdb Watchdog] Unexpected check error: {e}")

    def start_watchdog(self):
        """Start the background reconnect watchdog."""
        if not self._is_running:
            self._is_running = True
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())

    def stop_watchdog(self):
        """Stop the background reconnect watchdog."""
        self._is_running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()
            self._watchdog_task = None


wifi_adb_service = WifiAdbService()
