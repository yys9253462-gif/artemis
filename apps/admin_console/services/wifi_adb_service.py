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
import os
import re
import subprocess
import socket
from typing import Any
from artemis.toolchain import find_adb

logger = logging.getLogger("artemis.wifi_adb_service")


class WifiAdbService:
    """Manages wireless ADB scanning, pairing, and reconnect watchdog."""

    # A short interval makes a Wi-Fi drop recover almost immediately while
    # still leaving enough time for Android's wireless-debugging service to
    # reopen its socket after a roaming event.
    _WATCHDOG_INTERVAL_SECONDS = 2

    def __init__(self):
        self._watchdog_task: asyncio.Task | None = None
        self._is_running = False
        self._known_endpoints: set[str] = {
            endpoint.strip()
            for endpoint in os.getenv("ARTEMIS_WIFI_ADB_ENDPOINTS", "").split(",")
            if endpoint.strip()
        }
        self._scanning = False
        self._reconnect_lock = asyncio.Lock()

    def _persist_known_endpoints(self) -> None:
        """Keep reconnect targets across a UI-server restart."""
        from artemis.config.paths import get_env_file

        env_file = get_env_file()
        endpoints = ",".join(sorted(self._known_endpoints))
        lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
        key = "ARTEMIS_WIFI_ADB_ENDPOINTS="
        replacement = f"{key}{endpoints}"
        for index, line in enumerate(lines):
            if line.startswith(key):
                lines[index] = replacement
                break
        else:
            lines.append(replacement)
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

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
            self._persist_known_endpoints()
            logger.info(f"[WifiAdb] Successfully connected to {address}")
        return {
            "success": success,
            "address": address,
            "output": output
        }

    #: Android 11+ hands out the wireless-debugging connect port from this range.
    _SNIFF_PORT_RANGE: tuple[int, int] = (35000, 44000)
    _SNIFF_WORKERS = 300
    _SNIFF_TIMEOUT_SECONDS = 0.04

    def sniff_host_ports_fast(self, host_ip: str) -> list[int]:
        """Find the device's active wireless-debugging port in roughly a second.

        A 9000-port scan is the only way to discover the connect port that Android 11+
        randomises after pairing. Results come back through ``map`` rather than a shared
        list, and every socket is closed by its context manager, so an exception in one
        probe cannot leak a descriptor or corrupt the result set.
        """
        import concurrent.futures
        import socket

        def check_port(port: int) -> int | None:
            try:
                with socket.socket() as sock:
                    sock.settimeout(self._SNIFF_TIMEOUT_SECONDS)
                    return port if sock.connect_ex((host_ip, port)) == 0 else None
            except OSError:
                return None

        start, end = self._SNIFF_PORT_RANGE
        with concurrent.futures.ThreadPoolExecutor(max_workers=self._SNIFF_WORKERS) as ex:
            results = ex.map(check_port, range(start, end))
        return sorted(port for port in results if port is not None)

    async def pair_device(self, address: str, pairing_code: str, connect_port: str | None = None) -> dict[str, Any]:
        """Pair an Android 11+ wireless debugging device using IP:Port and Pairing Code, then auto-connect with ultra-fast port sniffing."""
        address = address.strip()
        pairing_code = pairing_code.strip()
        if not address or not pairing_code:
            return {"success": False, "message": "Address and pairing code are required."}

        code, stdout, stderr = await self.run_adb_cmd("pair", address, pairing_code)
        output = (stdout + stderr).strip()
        success = "successfully paired" in output.lower()

        connect_msg = ""
        connect_success = False
        connected_endpoint = None

        if success:
            host_ip = address.split(":")[0]
            pair_port_str = address.split(":")[1] if ":" in address else ""

            # Strategy 1: User explicitly provided connect_port
            if connect_port:
                candidate_endpoints = [f"{host_ip}:{connect_port}"]
            else:
                # Strategy 2: Ultra-fast (1s) multi-thread socket sniffer on host_ip
                await asyncio.sleep(0.5)
                open_ports = await asyncio.to_thread(self.sniff_host_ports_fast, host_ip)
                # Exclude the temporary pairing port itself
                comm_ports = [p for p in open_ports if str(p) != pair_port_str]
                
                # If sniffer found candidate ports, try them first; then fallback to mDNS or 5555
                candidate_endpoints = [f"{host_ip}:{p}" for p in comm_ports]
                
                # Check mDNS as auxiliary
                mdns_list = await self.scan_mdns_services()
                for item in mdns_list:
                    ep = item.get("endpoint", "")
                    if ep.startswith(host_ip + ":") and ep not in candidate_endpoints and ep != address:
                        candidate_endpoints.append(ep)

                # Fallback to standard 5555
                if f"{host_ip}:5555" not in candidate_endpoints:
                    candidate_endpoints.append(f"{host_ip}:5555")

            logger.info(f"[WifiAdb] Attempting auto-connection to candidate endpoints: {candidate_endpoints}")

            # Try connecting until one succeeds
            for target_ep in candidate_endpoints:
                conn_res = await self.connect_device(target_ep)
                if conn_res.get("success", False):
                    connect_success = True
                    connect_msg = conn_res.get("output", "")
                    connected_endpoint = target_ep
                    logger.info(f"[WifiAdb] Successfully auto-connected to {target_ep} after pairing!")
                    break

            # Disconnect any accidental offline connection to the temporary pairing port
            try:
                await self.run_adb_cmd("disconnect", address)
            except Exception:
                pass

        return {
            "success": success,
            "address": address,
            "output": output,
            "connect_success": connect_success,
            "connect_message": connect_msg,
            "connected_endpoint": connected_endpoint
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
                await asyncio.sleep(self._WATCHDOG_INTERVAL_SECONDS)
                devices = await self.get_connected_devices()
                online_serials = {d["serial"] for d in devices if d["state"] == "device"}

                missing = set(self._known_endpoints) - online_serials
                if missing:
                    # A reconnect can include an mDNS scan. Serialize it so a
                    # 2-second poll never creates overlapping ADB processes.
                    async with self._reconnect_lock:
                        for endpoint in missing:
                            logger.info(f"[WifiAdb Watchdog] Reconnecting offline device: {endpoint}")
                            result = await self.connect_device(endpoint)
                            if not result.get("success"):
                                # Android 11+ may change its connect port after a
                                # Wi-Fi transition; mDNS is the authoritative
                                # rediscovery path in that case.
                                await self.auto_discover_and_connect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[WifiAdb Watchdog] Unexpected check error: {e}")

    def start_watchdog(self):
        """Start the background reconnect watchdog."""
        if not self._is_running:
            self._is_running = True
            self._watchdog_task = asyncio.create_task(self._watchdog_loop())
            # A fresh install has no persisted endpoint yet. Paired Android
            # 11+ devices advertise their current dynamic port over mDNS, so
            # discover it once instead of waiting for a manual reconnect.
            asyncio.create_task(self.auto_discover_and_connect())

    def stop_watchdog(self):
        """Stop the background reconnect watchdog."""
        self._is_running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()
            self._watchdog_task = None


wifi_adb_service = WifiAdbService()
