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

"""One-shot startup check that the configured LLM credential actually works.

A rotated or revoked relay key used to surface only as *every task failing mid-run*
with ``HTTP 401 INVALID_API_KEY`` -- the readiness report stayed green because it
only checked that a key was *present*, never that it was *accepted*. This check
costs a single metadata request at startup, logs a prominent warning, and pushes an
SSE event so the console can say so before the user queues any work.

It is deliberately fail-open: any transport problem is reported as "unverified",
never as "invalid", so a flaky network cannot block the server from starting.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from artemis.config import get_default_llm_config, settings
from artemis.utils.credentials_validator import validate_api_key
from artemis.utils.logger import get_logger

logger = get_logger(__name__)

#: Auth failures that mean "this key will never work" rather than "try again later".
REJECTION_MARKERS = ("401", "403", "invalid_api_key", "invalid api key", "unauthorized")

DEFAULT_TIMEOUT_SECONDS = 12.0


@dataclass(frozen=True)
class CredentialSelfCheckResult:
    """Outcome of the startup credential probe."""

    status: str  # "ok" | "rejected" | "missing" | "unverified"
    provider: str
    model: str
    message: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def rejected(self) -> bool:
        """True only when the provider explicitly refused the credential."""
        return self.status == "rejected"

    def to_event(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "message": self.message,
        }


def _base_url_for(provider: str) -> str | None:
    """Endpoint the provider will actually be called on.

    OpenAI-compatible providers share ``OPENAI_BASE_URL``; that is the relay
    deployment's entry point, so validating against ``api.openai.com`` would report
    a perfectly good relay key as broken.
    """
    if provider in ("openai", "custom", "ollama", "vllm"):
        value = getattr(settings, "OPENAI_BASE_URL", None)
        return str(value) if value else None
    return None


def _active_target() -> tuple[str, str, str] | None:
    """(provider, model, api_key) of the model the system will use most, or None."""
    try:
        agent_cfg = get_default_llm_config().get_agent("planner")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.debug(f"Credential self-check could not read the LLM config: {exc}")
        return None

    provider = str(getattr(agent_cfg, "provider", "") or "").strip().lower()
    model = str(getattr(agent_cfg, "model", "") or "").strip()
    if not provider:
        return None

    key_obj = settings.get_api_key(provider)
    api_key = key_obj.get_secret_value().strip() if key_obj else ""
    return provider, model, api_key


async def run_credential_selfcheck(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> CredentialSelfCheckResult:
    """Verify the active LLM credential once. Never raises."""
    target = _active_target()
    if target is None:
        return CredentialSelfCheckResult(
            status="unverified",
            provider="unknown",
            model="",
            message="无法读取当前模型配置，跳过启动凭证自检。",
        )

    provider, model, api_key = target
    if not api_key:
        return CredentialSelfCheckResult(
            status="missing",
            provider=provider,
            model=model,
            message=f"未配置 {provider} 的 API Key，任何任务都会在调用模型时失败。",
        )

    started = time.monotonic()
    try:
        valid, message = await validate_api_key(
            provider, api_key, base_url=_base_url_for(provider), timeout=timeout
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Fail open: a transport problem is not evidence the key is bad.
        logger.debug(f"Credential self-check transport error: {exc}")
        return CredentialSelfCheckResult(
            status="unverified",
            provider=provider,
            model=model,
            message=f"凭证自检未能完成（网络或端点异常）：{exc}",
        )

    elapsed = time.monotonic() - started
    if valid:
        logger.info(
            f"[CredentialSelfCheck] {provider}/{model} credential accepted "
            f"({elapsed:.2f}s)."
        )
        return CredentialSelfCheckResult(
            status="ok", provider=provider, model=model, message=message
        )

    lowered = message.lower()
    if any(marker in lowered for marker in REJECTION_MARKERS):
        logger.error(
            f"[CredentialSelfCheck] {provider}/{model} credential was REJECTED: {message}. "
            "Tasks will fail with an authentication error until the key is replaced."
        )
        return CredentialSelfCheckResult(
            status="rejected", provider=provider, model=model, message=message
        )

    logger.warning(
        f"[CredentialSelfCheck] {provider}/{model} credential could not be verified: {message}"
    )
    return CredentialSelfCheckResult(
        status="unverified", provider=provider, model=model, message=message
    )


async def run_and_announce(timeout: float = DEFAULT_TIMEOUT_SECONDS) -> CredentialSelfCheckResult:
    """Run the check and, when the credential is refused, tell connected clients."""
    result = await run_credential_selfcheck(timeout=timeout)
    if result.ok or result.status == "unverified":
        return result
    try:
        from apps.admin_console.services.task_queue_service import task_queue_service

        task_queue_service._broadcast_event("credential_warning", result.to_event())
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.debug(f"Could not broadcast credential warning: {exc}")
    return result
