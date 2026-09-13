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

"""Engine-selection contracts for the agents that can run on two engines.

Both ``Explorer`` and ``VideoAnalyzer`` prefer the native google-genai SDK when a
Google API key (or a pooled client on the context) is available, and otherwise fall
back to the universal LangChain path. That branch had no direct coverage, which is
precisely how twelve Explorer / VideoAnalyzer tests stayed red for a long time:
they mocked the native client while the agents silently ran the LangChain loop.

These tests pin the decision itself, so a future change to the fallback rule fails
here -- loudly and in one place -- instead of scattering misleading failures across
the agent suites.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from artemis.agents.explorer.explorer import Explorer
from artemis.agents.video_analyzer.video_analyzer import VideoAnalyzer

GEMINI_MODEL = "gemini-3.7-flash"
NON_GEMINI_MODEL = "gpt-4o"


# --------------------------------------------------------------------------- #
# Explorer._detect_native_engine
# --------------------------------------------------------------------------- #


def _explorer(model: str, *, client: object | None = None) -> Explorer:
    """An Explorer carrying only the state ``_detect_native_engine`` reads."""
    explorer = Explorer.__new__(Explorer)
    explorer.ctx = SimpleNamespace(_genai_client=client)
    explorer.model_name = model
    return explorer


def test_explorer_non_gemini_model_never_uses_native():
    """A non-Gemini model cannot be driven by the google-genai SDK, key or not."""
    explorer = _explorer(NON_GEMINI_MODEL, client=MagicMock())
    with patch(
        "artemis.agents.explorer.explorer.settings.GOOGLE_API_KEY", SecretStr("k")
    ):
        assert explorer._detect_native_engine() is False


def test_explorer_shared_client_forces_native_without_google_key():
    """A pooled client on the context is enough -- this is the relay deployment path."""
    client = MagicMock()
    explorer = _explorer(GEMINI_MODEL, client=client)
    with patch(
        "artemis.agents.explorer.explorer.settings.GOOGLE_API_KEY", None
    ):
        assert explorer._detect_native_engine() is True


def test_explorer_gemini_without_key_falls_back_to_universal():
    """No key and no pooled client: the SDK cannot be built, so LangChain runs."""
    explorer = _explorer(GEMINI_MODEL, client=None)
    with patch(
        "artemis.agents.explorer.explorer.settings.GOOGLE_API_KEY", None
    ):
        assert explorer._detect_native_engine() is False


def test_explorer_gemini_with_key_uses_native():
    explorer = _explorer(GEMINI_MODEL, client=None)
    with patch(
        "artemis.agents.explorer.explorer.settings.GOOGLE_API_KEY", SecretStr("k")
    ):
        assert explorer._detect_native_engine() is True


def test_explorer_empty_key_is_treated_as_absent():
    """An empty SecretStr must not select the native engine."""
    explorer = _explorer(GEMINI_MODEL, client=None)
    with patch(
        "artemis.agents.explorer.explorer.settings.GOOGLE_API_KEY", SecretStr("")
    ):
        assert explorer._detect_native_engine() is False


# --------------------------------------------------------------------------- #
# VideoAnalyzer._init_engine
# --------------------------------------------------------------------------- #


def _analyzer(model: str = GEMINI_MODEL, *, client: object | None = None) -> VideoAnalyzer:
    """A VideoAnalyzer carrying only the state ``_init_engine`` reads."""
    analyzer = VideoAnalyzer.__new__(VideoAnalyzer)
    analyzer.ctx = SimpleNamespace(
        _genai_client=client,
        llm_config=SimpleNamespace(
            utils=SimpleNamespace(video_analyzer=SimpleNamespace(model=model))
        ),
    )
    # The follow-up mode resolution needs a fully built config; it is a separate
    # contract and is exercised by the video-analyzer suite.
    analyzer._resolve_video_processing = lambda: None
    return analyzer


def test_video_analyzer_shared_client_selects_native_without_google_key():
    client = MagicMock()
    analyzer = _analyzer(client=client)
    with (
        patch("artemis.agents.video_analyzer.video_analyzer.settings.GOOGLE_API_KEY", None),
        patch("artemis.agents.video_analyzer.video_analyzer.genai.Client") as new_client,
    ):
        analyzer._init_engine()
        assert analyzer.use_native_gemini is True
        assert analyzer.client is client
        new_client.assert_not_called()  # the pooled client is reused


@pytest.mark.asyncio
async def test_video_analyzer_google_key_builds_and_pools_native_client():
    ctx_client = MagicMock()
    analyzer = _analyzer(client=None)
    with (
        patch(
            "artemis.agents.video_analyzer.video_analyzer.settings.GOOGLE_API_KEY",
            SecretStr("k"),
        ),
        patch(
            "artemis.agents.video_analyzer.video_analyzer.genai.Client",
            return_value=ctx_client,
        ) as new_client,
        patch(
            "artemis.agents.video_analyzer.video_analyzer.cleanup_abandoned_gemini_files",
            AsyncMock(),
        ),
    ):
        analyzer._init_engine()
        assert analyzer.use_native_gemini is True
        assert analyzer.client is ctx_client
        new_client.assert_called_once()
        # The client is shared on the context for connection pooling.
        assert analyzer.ctx._genai_client is ctx_client
        # Let the fire-and-forget cleanup task settle before the loop closes.
        await asyncio.sleep(0)


def test_video_analyzer_without_key_falls_back_to_universal():
    analyzer = _analyzer(client=None)
    with patch("artemis.agents.video_analyzer.video_analyzer.settings.GOOGLE_API_KEY", None):
        analyzer._init_engine()
        assert analyzer.use_native_gemini is False
        assert analyzer.client is None


def test_video_analyzer_non_gemini_model_falls_back_to_universal():
    analyzer = _analyzer(NON_GEMINI_MODEL, client=None)
    with patch(
        "artemis.agents.video_analyzer.video_analyzer.settings.GOOGLE_API_KEY",
        SecretStr("k"),
    ):
        analyzer._init_engine()
        assert analyzer.use_native_gemini is False


def test_video_analyzer_client_construction_failure_falls_back_gracefully():
    """A broken client must degrade to the universal engine, never raise."""
    analyzer = _analyzer(client=None)
    with (
        patch(
            "artemis.agents.video_analyzer.video_analyzer.settings.GOOGLE_API_KEY",
            SecretStr("k"),
        ),
        patch(
            "artemis.agents.video_analyzer.video_analyzer.genai.Client",
            side_effect=RuntimeError("boom"),
        ),
    ):
        analyzer._init_engine()
        assert analyzer.use_native_gemini is False


def test_video_analyzer_strips_provider_prefix_from_model_name():
    analyzer = _analyzer("google/gemini-3.7-flash", client=None)
    with patch("artemis.agents.video_analyzer.video_analyzer.settings.GOOGLE_API_KEY", None):
        analyzer._init_engine()
        assert analyzer.model_name == GEMINI_MODEL
