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

"""Scheduler & Automation Engine for Artemis.

Features:
1. Schedule recurring automation tasks (daily at HH:MM, intervals in minutes/hours, cron-like).
2. Schedule one-off delayed tasks at a future timestamp.
3. Automatically triggers task execution through TaskQueueService.
4. Persistent task storage in JSON file with live execution history.
5. Inbound Webhook execution endpoint to trigger mobile automation via external triggers.
"""

import asyncio
import datetime
import json
import logging
import os
from pathlib import Path
import time
import uuid
from typing import Any

from artemis.config import TRACES_PATH, WORKSPACE_ROOT

logger = logging.getLogger("artemis.scheduler_service")


class ScheduledTask:
    def __init__(
        self,
        task_id: str,
        name: str,
        goal: str,
        schedule_type: str,  # "daily", "interval", "once"
        schedule_time: str,  # "08:30" or minutes as string or ISO datetime
        profile: str = "flash",
        device_serial: str | None = None,
        enabled: bool = True,
        created_at: float = 0.0,
        last_run_at: float | None = None,
        next_run_at: float | None = None,
        run_count: int = 0,
    ):
        self.task_id = task_id or str(uuid.uuid4())[:8]
        self.name = name or "未命名定时任务"
        self.goal = goal
        self.schedule_type = schedule_type
        self.schedule_time = schedule_time
        self.profile = profile or "flash"
        self.device_serial = device_serial
        self.enabled = enabled
        self.created_at = created_at or time.time()
        self.last_run_at = last_run_at
        self.next_run_at = next_run_at or self.calculate_next_run()
        self.run_count = run_count

    def calculate_next_run(self) -> float:
        """Calculate the next execution timestamp."""
        now = time.time()
        now_dt = datetime.datetime.now()

        if self.schedule_type == "daily":
            try:
                parts = self.schedule_time.strip().split(":")
                hour = int(parts[0])
                minute = int(parts[1]) if len(parts) > 1 else 0
                target = now_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target.timestamp() <= now:
                    target += datetime.timedelta(days=1)
                return target.timestamp()
            except Exception:
                return now + 86400

        elif self.schedule_type == "interval":
            try:
                mins = int(self.schedule_time)
                return now + max(1, mins) * 60
            except Exception:
                return now + 3600

        elif self.schedule_type == "once":
            try:
                target_dt = datetime.datetime.fromisoformat(self.schedule_time)
                return target_dt.timestamp()
            except Exception:
                return now + 60

        return now + 86400

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "goal": self.goal,
            "schedule_type": self.schedule_type,
            "schedule_time": self.schedule_time,
            "profile": self.profile,
            "device_serial": self.device_serial,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "run_count": self.run_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScheduledTask":
        return cls(
            task_id=data.get("task_id", ""),
            name=data.get("name", ""),
            goal=data.get("goal", ""),
            schedule_type=data.get("schedule_type", "daily"),
            schedule_time=data.get("schedule_time", "09:00"),
            profile=data.get("profile", "flash"),
            device_serial=data.get("device_serial"),
            enabled=data.get("enabled", True),
            created_at=data.get("created_at", time.time()),
            last_run_at=data.get("last_run_at"),
            next_run_at=data.get("next_run_at"),
            run_count=data.get("run_count", 0),
        )


class SchedulerService:
    """Centralized manager for scheduled and automated recurring mobile tasks."""

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}
        self._loop_task: asyncio.Task | None = None
        self._is_running = False
        self._storage_path = Path(TRACES_PATH) / "scheduled_tasks.json"

    def _load_tasks(self):
        """Load tasks from disk."""
        if self._storage_path.exists():
            try:
                content = self._storage_path.read_text(encoding="utf-8")
                raw_list = json.loads(content)
                self._tasks = {item["task_id"]: ScheduledTask.from_dict(item) for item in raw_list}
            except Exception as e:
                logger.error(f"[Scheduler] Failed to load scheduled tasks: {e}")
                self._tasks = {}

    def _save_tasks(self):
        """Persist tasks to disk."""
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            raw_list = [t.to_dict() for t in self._tasks.values()]
            self._storage_path.write_text(json.dumps(raw_list, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"[Scheduler] Failed to save scheduled tasks: {e}")

    def list_tasks(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in sorted(self._tasks.values(), key=lambda x: x.created_at, reverse=True)]

    def add_task(
        self,
        name: str,
        goal: str,
        schedule_type: str,
        schedule_time: str,
        profile: str = "flash",
        device_serial: str | None = None,
    ) -> dict[str, Any]:
        task = ScheduledTask(
            task_id=str(uuid.uuid4())[:8],
            name=name,
            goal=goal,
            schedule_type=schedule_type,
            schedule_time=schedule_time,
            profile=profile,
            device_serial=device_serial,
        )
        self._tasks[task.task_id] = task
        self._save_tasks()
        logger.info(f"[Scheduler] Added scheduled task '{task.name}' ({task.task_id}) next run at {task.next_run_at}")
        return task.to_dict()

    def delete_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save_tasks()
            return True
        return False

    def toggle_task(self, task_id: str, enabled: bool) -> bool:
        if task_id in self._tasks:
            self._tasks[task_id].enabled = enabled
            if enabled:
                self._tasks[task_id].next_run_at = self._tasks[task_id].calculate_next_run()
            self._save_tasks()
            return True
        return False

    async def trigger_task_immediately(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        return await self._execute_task(task)

    async def _execute_task(self, task: ScheduledTask) -> bool:
        """Enqueue task into Artemis task queue service."""
        try:
            from apps.admin_console.schemas.task_schema import RunRequest
            from apps.admin_console.services.task_queue_service import task_queue_service

            logger.info(f"[Scheduler] Executing scheduled automation task: '{task.name}' - Goal: {task.goal}")
            req = RunRequest(
                goal=task.goal,
                profile=task.profile,
                device_serial=task.device_serial,
            )
            # Enqueue into the existing unified queue service
            res = await task_queue_service.enqueue_task(req)
            task.last_run_at = time.time()
            task.run_count += 1
            if task.schedule_type == "once":
                task.enabled = False
            else:
                task.next_run_at = task.calculate_next_run()
            self._save_tasks()
            return True
        except Exception as e:
            logger.error(f"[Scheduler] Error triggering scheduled task {task.task_id}: {e}")
            return False

    async def _scheduler_loop(self):
        """Poll and check tasks every 10 seconds."""
        logger.info("[Scheduler] Automation scheduler loop active.")
        while self._is_running:
            try:
                now = time.time()
                for task in list(self._tasks.values()):
                    if task.enabled and task.next_run_at and now >= task.next_run_at:
                        logger.info(f"[Scheduler] Scheduled time reached for: {task.name}")
                        await self._execute_task(task)
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[Scheduler] Unexpected error in loop: {e}")
                await asyncio.sleep(10)

    def start(self):
        if not self._is_running:
            self._load_tasks()
            self._is_running = True
            self._loop_task = asyncio.create_task(self._scheduler_loop())

    def stop(self):
        self._is_running = False
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None


scheduler_service = SchedulerService()
