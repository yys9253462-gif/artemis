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

from pathlib import Path

from jinja2 import Template
from langchain_core.messages import HumanMessage, SystemMessage
from artemis.context import ArtemisContext
from artemis.data_engine.trace import trace
from artemis.services.llm import get_llm, invoke_llm_with_timeout_message, with_fallback
from artemis.utils.logger import get_logger
from pydantic import BaseModel, Field

logger = get_logger(__name__)


class _CyFunctionDetectorMeta(type):
    def __instancecheck__(self, instance):
        name = type(instance).__name__
        return (
            name
            in (
                "cyfunction",
                "cython_function_or_method",
                "builtin_function_or_method",
            )
            or "cyfunction" in name.lower()
        )


class CyFunctionDetector(metaclass=_CyFunctionDetectorMeta):
    pass


class HopperOutput(BaseModel):
    model_config = {"ignored_types": (CyFunctionDetector,)}
    found: bool = Field(description="True if the requested data was found, False otherwise.")
    output: str | None = Field(description="The extracted data if found, null otherwise.")
    reason: str = Field(
        description="A short explanation of what you looked for"
        + " and how you decided what to extract."
    )


@trace(type="agent", name="hopper")
async def hopper(
    ctx: ArtemisContext,
    request: str,
    data: str,
    use_fallback: bool = True,
) -> HopperOutput:
    logger.info(f"Starting Hopper Agent (use_fallback={use_fallback})")
    system_message = Template(
        Path(__file__).parent.joinpath("hopper.md").read_text(encoding="utf-8")
    ).render() + "\n\nCRITICAL: Respond ONLY with a valid JSON markdown block containing fields 'found', 'output', and 'reason'."
    messages = [
        SystemMessage(content=system_message),
        HumanMessage(content=f"{request}\nHere is the data you must dig:\n{data}"),
    ]

    from artemis.llm.structured import parse_structured
    base_llm = get_llm(ctx=ctx, name="hopper", is_utils=True)
    try:
        if use_fallback:
            base_fallback = get_llm(ctx=ctx, name="hopper", is_utils=True, use_fallback=True)
            res = await with_fallback(
                main_call=lambda: invoke_llm_with_timeout_message(base_llm.ainvoke(messages)),
                fallback_call=lambda: invoke_llm_with_timeout_message(base_fallback.ainvoke(messages)),
            )
        else:
            res = await invoke_llm_with_timeout_message(base_llm.ainvoke(messages))

        # Check if the result was already parsed (e.g. tool call or structured)
        if isinstance(res, HopperOutput):
            return res

        # Extract text content and parse via robust parser
        raw_text = res.content if hasattr(res, "content") else str(res)
        parsed = parse_structured(raw_text, HopperOutput)
        if not isinstance(parsed, HopperOutput):
            # If tool calls were returned instead of text
            if hasattr(res, "tool_calls") and res.tool_calls:
                args = res.tool_calls[0].get("args", {})
                return HopperOutput(**args)
            return HopperOutput(found=False, output=None, reason="Failed to parse structured JSON response")
        return parsed
    except Exception as e:
        logger.error(f"Hopper LLM invocation failed: {e}")
        return HopperOutput(
            found=False,
            output=None,
            reason=f"Failed due to LLM error: {str(e)[:500]}",
        )
