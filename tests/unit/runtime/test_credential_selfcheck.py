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

"""Startup credential self-check.

A rotated relay key used to surface only as every task failing mid-run with
HTTP 401, while readiness stayed green because it never verified the key. These
tests pin the three outcomes the check must distinguish -- accepted, rejected,
unverifiable -- and the promise that a transport problem is never reported as an
invalid credential.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from artemis.runtime import credential_selfcheck as check


def _agent_cfg(provider: str = "openai", model: str = "gemini-3.8-flash-high"):
    return SimpleNamespace(provider=provider, model=model)


def _patch_api_key(value):
    """Patch the settings accessor. It is a class method, so the *type* is patched --
    patching it on the instance makes mock's restore step raise AttributeError."""
    return patch.object(type(check.settings), "get_api_key", return_value=value)


def _patch_config(agent_cfg=None):
    """Patch the LLM config lookup used to find the active provider/model."""
    cfg = MagicMock()
    cfg.get_agent.return_value = agent_cfg if agent_cfg is not None else _agent_cfg()
    return patch.object(check, "get_default_llm_config", return_value=cfg)


# --------------------------------------------------------------------------- #
# Endpoint resolution
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("provider", ["openai", "custom", "ollama", "vllm"])
def test_openai_compatible_providers_use_the_configured_relay(provider):
    """Validating against api.openai.com would call a good relay key broken."""
    with patch.object(check.settings, "OPENAI_BASE_URL", "https://relay.example/v1"):
        assert check._base_url_for(provider) == "https://relay.example/v1"


@pytest.mark.parametrize("provider", ["google", "gemini", "anthropic", "xai"])
def test_other_providers_have_no_endpoint_override(provider):
    assert check._base_url_for(provider) is None


def test_endpoint_is_none_when_relay_is_unset():
    with patch.object(check.settings, "OPENAI_BASE_URL", None):
        assert check._base_url_for("openai") is None


# --------------------------------------------------------------------------- #
# Active target resolution
# --------------------------------------------------------------------------- #


def test_active_target_reads_provider_model_and_key():
    with (
        _patch_config(_agent_cfg("openai", "relay-model")),
        _patch_api_key(SecretStr("sk-live")),
    ):
        assert check._active_target() == ("openai", "relay-model", "sk-live")


def test_active_target_returns_none_without_a_provider():
    with _patch_config(_agent_cfg(provider="")):
        assert check._active_target() is None


def test_active_target_survives_a_broken_config():
    """A config failure must not crash startup."""
    with patch.object(check, "get_default_llm_config", side_effect=RuntimeError("boom")):
        assert check._active_target() is None


# --------------------------------------------------------------------------- #
# Outcomes
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_missing_key_is_reported_as_missing():
    with (
        _patch_config(),
        _patch_api_key(None),
    ):
        result = await check.run_credential_selfcheck()
    assert result.status == "missing"
    assert result.rejected is False


@pytest.mark.asyncio
async def test_accepted_key_is_ok():
    with (
        _patch_config(),
        _patch_api_key(SecretStr("sk-live")),
        patch.object(check, "validate_api_key", AsyncMock(return_value=(True, "ok"))),
    ):
        result = await check.run_credential_selfcheck()
    assert result.status == "ok"
    assert result.ok is True


@pytest.mark.asyncio
async def test_401_is_reported_as_rejected():
    message = "OpenAI API verification failed (401): {'code': 'INVALID_API_KEY'}"
    with (
        _patch_config(),
        _patch_api_key(SecretStr("sk-dead")),
        patch.object(check, "validate_api_key", AsyncMock(return_value=(False, message))),
    ):
        result = await check.run_credential_selfcheck()
    assert result.status == "rejected"
    assert result.rejected is True


@pytest.mark.asyncio
async def test_transport_error_fails_open_as_unverified():
    """A network blip must never be reported as a bad credential."""
    with (
        _patch_config(),
        _patch_api_key(SecretStr("sk-live")),
        patch.object(check, "validate_api_key", AsyncMock(side_effect=OSError("timeout"))),
    ):
        result = await check.run_credential_selfcheck()
    assert result.status == "unverified"
    assert result.rejected is False


@pytest.mark.asyncio
async def test_non_auth_failure_is_unverified_not_rejected():
    """A 500 from the provider says nothing about the key itself."""
    with (
        _patch_config(),
        _patch_api_key(SecretStr("sk-live")),
        patch.object(
            check,
            "validate_api_key",
            AsyncMock(return_value=(False, "OpenAI API verification failed (500): oops")),
        ),
    ):
        result = await check.run_credential_selfcheck()
    assert result.status == "unverified"


# --------------------------------------------------------------------------- #
# Announcement
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_rejection_is_broadcast_to_clients():
    service = MagicMock()
    with (
        patch.object(
            check,
            "run_credential_selfcheck",
            AsyncMock(
                return_value=check.CredentialSelfCheckResult(
                    status="rejected", provider="openai", model="m", message="401"
                )
            ),
        ),
        patch(
            "apps.admin_console.services.task_queue_service.task_queue_service", service
        ),
    ):
        result = await check.run_and_announce()
    assert result.rejected is True
    service._broadcast_event.assert_called_once()
    event_type, payload = service._broadcast_event.call_args.args
    assert event_type == "credential_warning"
    assert payload["provider"] == "openai"


@pytest.mark.asyncio
async def test_success_is_not_broadcast():
    service = MagicMock()
    with (
        patch.object(
            check,
            "run_credential_selfcheck",
            AsyncMock(
                return_value=check.CredentialSelfCheckResult(
                    status="ok", provider="openai", model="m", message="fine"
                )
            ),
        ),
        patch(
            "apps.admin_console.services.task_queue_service.task_queue_service", service
        ),
    ):
        await check.run_and_announce()
    service._broadcast_event.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_failure_does_not_break_startup():
    with (
        patch.object(
            check,
            "run_credential_selfcheck",
            AsyncMock(
                return_value=check.CredentialSelfCheckResult(
                    status="missing", provider="openai", model="m", message="none"
                )
            ),
        ),
        patch(
            "apps.admin_console.services.task_queue_service.task_queue_service",
            side_effect=RuntimeError("no console"),
        ),
    ):
        result = await check.run_and_announce()
    assert result.status == "missing"
