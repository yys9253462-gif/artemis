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

from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from artemis.agents.hopper.hopper import HopperOutput, hopper
from artemis.context import ArtemisContext
from artemis.controllers.platform_specific_commands_controller import (
    list_packages_async,
)
from artemis.data_engine.trace import trace_langchain_tool
from artemis.drivers.base import BaseDeviceDriver
from artemis.graph.state import State
from artemis.tools.base import ArtemisTool, ToolCategory
from artemis.tools.tool_wrapper import ToolWrapper
from artemis.tools.types import CyFunctionDetector
from artemis.utils.app_launch_utils import launch_app_with_retries
from artemis.utils.logger import get_logger

logger = get_logger(__name__)


#: Chinese display-name -> candidate package ids, ordered longest-name-first so the
#: most specific alias wins (``美团外卖`` before ``美团``). Used as a zero-LLM fast path
#: for the apps this deployment drives most often; anything not listed falls through to
#: the Hopper resolver.
FAST_APP_ALIASES: dict[str, list[str]] = {
    "千牛工作台": ["com.taobao.qianniu"],
    "千牛卖家": ["com.taobao.qianniu"],
    "千牛": ["com.taobao.qianniu"],
    "抖店": [
        "com.bytedance.ecom.seller",
        "com.ss.android.ugc.aweme",
        "com.bytedance.compass",
    ],
    "抖音": ["com.ss.android.ugc.aweme"],
    "闲鱼": ["com.taobao.idlefish"],
    "淘宝": ["com.taobao.taobao"],
    "小红书": ["com.xingin.xhs"],
    "微信": ["com.tencent.mm"],
    "拼多多": ["com.xunmeng.pinduoduo"],
    "京东": ["com.jingdong.app.mall"],
    "美团外卖": ["com.sankuai.meituan.takeoutnew"],
    "美团": ["com.sankuai.meituan"],
    "大众点评": ["com.dianping.v1"],
    "快手": ["com.smile.gifmaker"],
    "支付宝": ["com.alipay.android.phone.vendor", "com.eg.android.AlipayGphone"],
    "网易云音乐": ["com.netease.cloudmusic"],
    "网易云": ["com.netease.cloudmusic"],
    "qq音乐": ["com.tencent.qqmusic"],
    "哔哩哔哩": ["tv.danmaku.bili"],
    "b站": ["tv.danmaku.bili"],
    "微博": ["com.sina.weibo"],
}

#: Aliases shorter than this never match as a substring. A one-character alias such as
#: ``云`` would otherwise swallow unrelated names.
_MIN_ALIAS_SUBSTRING_LEN = 2


def _match_fast_alias(app_name: str, package_set: set[str]) -> str | None:
    """Resolve ``app_name`` against :data:`FAST_APP_ALIASES`, or ``None``.

    Exact (case-insensitive) matches win outright. Substring matching is one-directional
    -- the alias must appear inside the user's input -- and only for aliases of at least
    :data:`_MIN_ALIAS_SUBSTRING_LEN` characters, so "音乐" no longer silently resolves to
    QQ 音乐 via the reverse direction and short inputs do not collide.
    """
    norm = app_name.strip().lower()
    if not norm:
        return None

    def first_installed(candidates: list[str]) -> str | None:
        return next((c for c in candidates if c in package_set), None)

    exact = FAST_APP_ALIASES.get(norm)
    if exact is not None:
        hit = first_installed(exact)
        if hit:
            return hit

    for alias, candidates in FAST_APP_ALIASES.items():
        if len(alias) < _MIN_ALIAS_SUBSTRING_LEN or alias not in norm:
            continue
        hit = first_installed(candidates)
        if hit:
            return hit
    return None


class LaunchAppArgs(BaseModel):
    """Arguments schema for launching an application."""

    model_config = {"ignored_types": (CyFunctionDetector,)}
    app_name: str = Field(
        ...,
        description="The natural language name of the application to launch.",
    )


LAUNCH_APP_DOCSTRING = (
    "[ACTION] Finds and launches an application on the device using its natural language name."
)


async def find_package(ctx: ArtemisContext, app_name: str, use_fallback: bool = True) -> str | None:
    """Finds the package name for a given application name.

    Returns None if package not found or on error.
    """
    package_cache = getattr(ctx, "package_cache", None)
    if package_cache is None or not isinstance(package_cache, dict):
        try:
            ctx.package_cache = {}
            package_cache = ctx.package_cache
        except Exception:  # pylint: disable=broad-exception-caught
            package_cache = {}

    if isinstance(package_cache, dict) and app_name in package_cache:
        logger.info(f"Cache hit for app '{app_name}': {package_cache[app_name]}")
        return package_cache[app_name]

    try:
        all_packages = await list_packages_async(ctx=ctx)
        package_set = {p.strip() for p in all_packages.split("\n") if p.strip()}

        # Fast path 1: If app_name is already directly an installed package name
        if app_name in package_set:
            if isinstance(package_cache, dict):
                package_cache[app_name] = app_name
            return app_name

        # Fast path 2: Instant Zero-LLM alias lookup for high-frequency Chinese apps
        fast_hit = _match_fast_alias(app_name, package_set)
        if fast_hit:
            logger.info(f"[FastLauncher] Zero-LLM hit: '{app_name}' -> '{fast_hit}'")
            if isinstance(package_cache, dict):
                package_cache[app_name] = fast_hit
            return fast_hit

        hopper_output: HopperOutput = await hopper(
            ctx=ctx,
            request=(f"I'm looking for the package name of the following app: '{app_name}'"),
            data=all_packages,
            use_fallback=use_fallback,
        )
        if not hopper_output.found or not hopper_output.output:
            if isinstance(package_cache, dict):
                package_cache[app_name] = None
            return None

        package_name = hopper_output.output.strip()
        if package_name not in package_set:
            logger.warning(
                f"Hopper returned package '{package_name}' for '{app_name}', "
                "but it is NOT physically installed on the device!"
            )
            if isinstance(package_cache, dict):
                package_cache[app_name] = None
            return None

        if isinstance(package_cache, dict):
            package_cache[app_name] = package_name
        return package_name
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Failed to find package for '{app_name}': {e}")
        return None


class LaunchAppTool(ArtemisTool):
    """Universal tool for finding and launching an application on the device."""

    def __init__(self, category: ToolCategory = "action"):
        super().__init__(
            name="launch_app",
            description=LAUNCH_APP_DOCSTRING,
            args_schema=LaunchAppArgs,
            category=category,
        )

    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    async def execute(
        self,
        driver: BaseDeviceDriver | None = None,
        ctx: ArtemisContext | None = None,
        app_name: str | None = None,
        tool_call_id: str | None = None,
        state: State | None = None,
        **kwargs: Any,
    ) -> Any:
        app = (
            app_name
            if app_name is not None
            else (kwargs.get("app_name") or kwargs.get("AppName") or "")
        )
        tcid = tool_call_id if tool_call_id is not None else kwargs.get("tool_call_id")
        st = state if state is not None else kwargs.get("state")

        success = False
        error_msg = None

        try:
            if not app:
                raise ValueError("app_name parameter is required.")

            if ctx is not None:
                package_name = await find_package(ctx=ctx, app_name=app)
                if not package_name:
                    success = False
                    outcome = f"Failed to launch app '{app}': Package not found."
                    error_msg = "Package not found."
                else:
                    success, error_msg = await launch_app_with_retries(
                        ctx=ctx, app_package=package_name
                    )
                    outcome = (
                        f"Launched app '{app}' ({package_name}); foreground confirmed."
                        if success
                        else f"Failed to launch app '{app}': {error_msg}"
                    )
            elif driver is not None and hasattr(driver, "launch_app"):
                success = await driver.launch_app(app)
                outcome = f"Launched app '{app}'." if success else f"Failed to launch app '{app}'."
                error_msg = None if success else "Launch failed."
            else:
                success = False
                outcome = "Error during launch app: No driver or context provided."
                error_msg = "No driver or context provided."
        except Exception as e:  # pylint: disable=broad-exception-caught
            success = False
            outcome = f"Error during launch app: {e}"
            error_msg = str(e)

        if st is not None:
            additional_kwargs = {} if success else ({"error": error_msg} if error_msg else {})
            return ToolMessage(
                tool_call_id=tcid or "",
                content=outcome,
                additional_kwargs=additional_kwargs,
                status="success" if success else "error",
            )

        return outcome


# Universal tool instance & aliases
launch_app = LaunchAppTool()
LaunchApp = LaunchAppTool


def get_launch_app_tool(ctx: ArtemisContext) -> BaseTool:
    """Exports launch_app as a LangChain BaseTool."""
    return trace_langchain_tool(launch_app.to_langchain_tool(ctx), ctx)


launch_app_wrapper = ToolWrapper(
    tool_fn_getter=get_launch_app_tool,
    on_success_fn=lambda *args, **kwargs: "Launch dispatched",
    on_failure_fn=lambda *args, **kwargs: "Failure",
)
