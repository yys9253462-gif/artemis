# Copyright 2025-2026 Minitap, Inc.
# Modifications Copyright 2026 Google LLC
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
#
# Originally from mobile-use (https://github.com/minitap-ai/mobile-use).
# See third_party/mobile_use/METADATA for the upstream source and local modifications.

"""Resolve a natural-language app name to an installed package via the Hopper agent."""

from artemis.context import ArtemisContext
from third_party.mobile_use.agents.hopper.hopper import HopperOutput, hopper
from third_party.mobile_use.controllers.platform_specific_commands_controller import (
    list_packages_async,
)
from third_party.mobile_use.utils.logger import get_logger

logger = get_logger(__name__)

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

_MIN_ALIAS_SUBSTRING_LEN = 2


def _match_fast_alias(app_name: str, package_set: set[str]) -> str | None:
    """优先精确匹配中文应用别名，再按单向子串匹配已安装应用。"""
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

        # Fast path: If app_name is already directly an installed package name
        if app_name in package_set:
            if isinstance(package_cache, dict):
                package_cache[app_name] = app_name
            return app_name

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
