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

"""E-Commerce & Social Cross-App Migration & Auto-Relist Pipeline.

Features:
1. Cross-platform product data extraction & intermediate buffer (Title, Price, Images, Specs).
2. Automated listing assistant for Taobao Qianniu (千牛), IdleFish (闲鱼), Xiaohongshu (小红书).
3. Image collection & local gallery staging for auto-fill in seller centers.
4. Pre-configured multi-step workflows with atomic checkpoints and self-recovery.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
import time
from typing import Any
from pydantic import BaseModel, Field

from artemis.config import TRACES_PATH

logger = logging.getLogger("artemis.ecommerce_migration")


class ProductListingItem(BaseModel):
    """Normalized structured product entity for cross-app relisting."""

    source_app: str = "doudian"
    title: str
    price: float | None = None
    category: str | None = None
    description: str | None = None
    main_images: list[str] = Field(default_factory=list)
    detail_images: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    target_app: str = "qianniu"  # "qianniu" or "idlefish" or "xhs"
    created_at: float = Field(default_factory=time.time)


class EcommerceMigrationService:
    """Manages cross-app e-commerce product staging, image assets, and automation prompts."""

    def __init__(self):
        self.storage_dir = Path(TRACES_PATH) / "ecommerce_staging"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.active_items: dict[str, ProductListingItem] = {}

    def save_staged_product(self, item_id: str, item: ProductListingItem) -> str:
        """Save extracted product details to intermediate staging buffer."""
        self.active_items[item_id] = item
        file_path = self.storage_dir / f"{item_id}.json"
        file_path.write_text(item.model_dump_json(indent=2), encoding="utf-8")
        logger.info(f"[EcommerceMigration] Staged product '{item.title}' for relisting to {item.target_app}")
        return str(file_path)

    def load_staged_product(self, item_id: str) -> ProductListingItem | None:
        if item_id in self.active_items:
            return self.active_items[item_id]
        file_path = self.storage_dir / f"{item_id}.json"
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                item = ProductListingItem(**data)
                self.active_items[item_id] = item
                return item
            except Exception as e:
                logger.error(f"[EcommerceMigration] Error loading staged product: {e}")
        return None

    @staticmethod
    def generate_migration_prompt(
        source_app_name: str,
        target_app_name: str,
        product_keyword: str | None = None,
        custom_instructions: str | None = None,
    ) -> str:
        """Generate high-precision structured goal for Artemis multi-agent executor."""
        base_prompt = (
            f"【跨平台电商全流程搬家任务】\n"
            f"1. 首先启动 {source_app_name}，"
        )
        if product_keyword:
            base_prompt += f"进入商品管理或店铺后台，搜索并打开商品「{product_keyword}」；\n"
        else:
            base_prompt += "进入商品管理或最近在售列表，选择第一件待同步商品并进入编辑/详情页；\n"

        base_prompt += (
            f"2. 获取该商品的完整标题、分类类目、销售价格以及主图详情图（截图或保存原图至手机相册）；\n"
            f"3. 返回手机主屏幕并启动目标店铺管理工具 {target_app_name}；\n"
            f"4. 进入【商品发布/新增宝贝】页面，自动填入对应的商品标题与价格，选择同类目，"
            f"并从相册选择刚保存的商品主图，最后存为草稿或提交审核。\n"
        )
        if custom_instructions:
            base_prompt += f"附加要求：{custom_instructions.strip()}"

        return base_prompt


ecommerce_migration_service = EcommerceMigrationService()
