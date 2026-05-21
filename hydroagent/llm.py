"""
Author: HydroAgent Team
Date: 2026-02-08
Description: LLM client with function calling support and prompt-based fallback.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """A single tool call from the LLM."""
    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass
class LLMResponse:
    """Parsed LLM response."""
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    thinking: str | None = None   # reasoning/thinking content (reasoning models only)

    def is_text(self) -> bool:
        return len(self.tool_calls) == 0 and self.text is not None

    def is_tool_call(self) -> bool:
        return len(self.tool_calls) > 0


class TokenTracker:
    """Track token usage across API calls.

    Tracks both session-level totals AND per-call breakdown so downstream
    metrics (e.g. tokens_per_useful_step) can attribute cost to specific
    agent turns. Also captures `cached_tokens` from providers that report
    it (OpenAI, DeepSeek, Qwen via Dashscope OpenAI-compat endpoint).
    """

    def __init__(self):
        self.total_prompt = 0
        self.total_completion = 0
        self.total_cached = 0
        self.call_count = 0
        # Per-call records (most recent call last)
        self.calls: list[dict] = []

    def record(self, prompt: int, completion: int, cached: int = 0):
        self.total_prompt += prompt
        self.total_completion += completion
        self.total_cached += cached
        self.call_count += 1
        self.calls.append({
            "prompt": prompt,
            "completion": completion,
            "cached": cached,
        })

    def last_call(self) -> dict:
        """Return the most recent call's token breakdown (empty dict if none)."""
        return self.calls[-1] if self.calls else {}

    @property
    def total(self) -> int:
        return self.total_prompt + self.total_completion

    def reset(self):
        """Reset counters for a new session."""
        self.total_prompt = 0
        self.total_completion = 0
        self.total_cached = 0
        self.call_count = 0
        self.calls.clear()

    def summary(self) -> dict:
        return {
            "calls": self.call_count,
            "prompt_tokens": self.total_prompt,
            "completion_tokens": self.total_completion,
            "cached_tokens": self.total_cached,
            "total_tokens": self.total,
        }


# ── Model profile detection ────────────────────────────────────────────────────
# Reasoning models (CoT baked-in, best at temperature=0):
_REASONING_KEYWORDS = ("r1", "r2", "r3", "qwq", "o1", "o3", "o4", "thinking", "reason")
# Dialogue/chat models (benefit from slight creativity, temperature ~0.3):
_DIALOGUE_KEYWORDS = ("v3", "v3.1", "gpt-4o", "gpt-4", "qwen", "claude", "gemini", "llama")


def model_profile(model_name: str) -> dict:
    """Detect model capabilities and return recommended inference parameters.

    Returns:
        {"type": "reasoning"|"dialogue"|"unknown",
         "temperature": float,    -- recommended default temperature
         "is_reasoning": bool}    -- True = model does explicit chain-of-thought
    """
    name = model_name.lower()
    if any(kw in name for kw in _REASONING_KEYWORDS):
        return {"type": "reasoning", "temperature": 0.0, "is_reasoning": True}
    if any(kw in name for kw in _DIALOGUE_KEYWORDS):
        return {"type": "dialogue", "temperature": 0.3, "is_reasoning": False}
    return {"type": "unknown", "temperature": 0.1, "is_reasoning": False}


def detect_reasoning_style(model_name: str) -> str | None:
    """Detect the thinking/reasoning API style for a model.

    Three styles are recognized:
      "deepseek_r1"      -- DeepSeek-R1/R2/R3: model embeds <think>...</think> in
                            text content; just parse and strip it, no extra API params.
      "qwen_thinking"    -- QwQ / Qwen3-thinking: pass extra_body={"enable_thinking": True}
                            via Dashscope OpenAI-compat endpoint; read reasoning_content field.
      "openai_reasoning" -- OpenAI o1/o3/o4: use reasoning_effort param, omit temperature.

    Returns None for standard dialogue models.
    """
    name = model_name.lower()
    # DeepSeek reasoning series: deepseek-r1, deepseek-r2, deepseek-r1-distill-*, etc.
    # These embed <think>...</think> in content and must NOT have reasoning_content
    # passed back.
    if "deepseek" in name and any(f"-r{d}" in name or f"_r{d}" in name for d in "123"):
        return "deepseek_r1"
    # DeepSeek V4+ thinking-by-default (e.g. deepseek-v4-flash): server returns
    # reasoning_content and *requires* it echoed back in subsequent turns.
    if "deepseek" in name and any(f"v{d}" in name for d in "456789"):
        return "deepseek_thinking"
    # QwQ (Qwen with thinking): qwq-32b, qwq-plus, etc.
    if "qwq" in name:
        return "qwen_thinking"
    # OpenAI o-series: o1-mini, o1-preview, o3-mini, o4-mini, o1, o3, o4, etc.
    if any(f"-o{d}" in name or name.startswith(f"o{d}") for d in "134"):
        return "openai_reasoning"
    return None


class LLMClient:
    """Unified LLM client supporting function calling and prompt-based fallback.

    Mode A: Native function calling (OpenAI, Qwen with tools support)
    Mode B: Prompt-based fallback (Ollama, models without tools support)

    Temperature is auto-set based on model type if not explicitly provided in config:
      - Reasoning models (DeepSeek-R1, QwQ, o1, ...): temperature=0.0
      - Dialogue models (DeepSeek-V3, Qwen, GPT-4o, ...): temperature=0.3
      - Unknown models: temperature=0.1 (conservative default)
    Set "temperature" explicitly in config to override this behavior.
    """

    def __init__(self, config: dict):
        self.model = config.get("model", "deepseek-v3.1")
        self.base_url = config.get("base_url")
        self.api_key = config.get("api_key")

        # Auto-set temperature from model profile unless explicitly configured
        _profile = model_profile(self.model)
        self._model_type = _profile["type"]
        self._is_reasoning_model = _profile["is_reasoning"]
        if "temperature" in config:
            self.temperature = config["temperature"]
        else:
            self.temperature = _profile["temperature"]
            logger.info(
                "[llm] model_profile('%s') -> type=%s, temperature=%.1f",
                self.model, self._model_type, self.temperature,
            )

        self.max_tokens = config.get("max_tokens", 20000)
        self.timeout = config.get("timeout", 120)
        self.max_retries = config.get("max_retries", 1)
        self.tokens = TokenTracker()

        # Rate limiting: min seconds between consecutive API calls
        self._request_interval: float = config.get("request_interval", 0.5)
        # 429 retry: wait `rate_limit_delay` seconds, double each retry, up to `rate_limit_retries`
        self._rate_limit_retries: int = config.get("rate_limit_retries", 3)
        self._rate_limit_delay: float = config.get("rate_limit_delay", 30.0)
        self._last_call_time: float = 0.0

        # Reasoning style: how to invoke and parse thinking for this model
        # Can be overridden in config via "reasoning_style": "deepseek_r1"|"qwen_thinking"|"openai_reasoning"|"none"
        style_cfg = config.get("reasoning_style")
        if style_cfg == "none":
            self._reasoning_style: str | None = None
        elif style_cfg:
            self._reasoning_style = style_cfg
        else:
            self._reasoning_style = detect_reasoning_style(self.model)

        if self._reasoning_style:
            logger.info(
                "[llm] reasoning_style='%s' for model '%s'",
                self._reasoning_style, self.model,
            )

        # Auto-detect or use config
        self._supports_fc = config.get("supports_function_calling")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            kwargs = {
                "api_key": self.api_key,
                "max_retries": self.max_retries,
                "timeout": self.timeout,
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
            logger.info(
                f"LLM client initialized: model={self.model}, "
                f"base_url={self.base_url}, timeout={self.timeout}s, "
                f"max_retries={self.max_retries}"
            )
        return self._client

    @property
    def supports_function_calling(self) -> bool:
        if self._supports_fc is None:
            # Auto-detect: try function calling, fallback if it fails
            self._supports_fc = self._detect_function_calling()
        return self._supports_fc

    @property
    def needs_reasoning_echo(self) -> bool:
        """True if the model requires reasoning_content echoed back in assistant
        turns (DeepSeek V4+ thinking mode). R1/qwen_thinking do NOT need this.
        """
        return self._reasoning_style == "deepseek_thinking"

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Send messages to LLM and get response.

        Args:
            messages: Chat messages in OpenAI format.
            tools: Tool schemas in OpenAI function calling format.
            temperature: Override default temperature.

        Returns:
            LLMResponse with either text or tool_calls.
        """
        temp = temperature if temperature is not None else self.temperature

        if tools and self.supports_function_calling:
            return self._chat_with_tools(messages, tools, temp)
        elif tools:
            return self._chat_with_prompt_tools(messages, tools, temp)
        else:
            return self._chat_text(messages, temp)

    def _create_completion(self, **kwargs):
        """Single entry point for all API calls: enforces request interval and retries on 429.

        Distinguishes two types of 429:
          - insufficient_quota: quota exhausted, retrying is futile -> raise immediately
            with a clear message so the experiment fails fast instead of wasting wait time.
          - rate_limit / too_many_requests: TPM/TPS throttle -> retry with exponential backoff.
        """
        # Enforce minimum interval between consecutive calls
        elapsed = time.time() - self._last_call_time
        if elapsed < self._request_interval:
            time.sleep(self._request_interval - elapsed)

        delay = self._rate_limit_delay
        for attempt in range(self._rate_limit_retries + 1):
            try:
                self._last_call_time = time.time()
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:
                err_str = str(e)

                # Quota exhausted: no point retrying, fail immediately
                if "insufficient_quota" in err_str.lower():
                    logger.error(
                        "API quota exhausted (insufficient_quota). "
                        "Please check your account balance or wait for quota reset. "
                        "Original error: %s", err_str,
                    )
                    raise

                is_rate_limit = (
                    "429" in err_str
                    or "rate_limit" in err_str.lower()
                    or "too many requests" in err_str.lower()
                )
                if is_rate_limit and attempt < self._rate_limit_retries:
                    logger.warning(
                        "Rate limit hit (429). Waiting %.0fs before retry %d/%d...",
                        delay, attempt + 1, self._rate_limit_retries,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 300)  # cap at 5 min
                    continue
                raise

    def _reasoning_extra_kwargs(self) -> dict:
        """Return extra API kwargs needed to activate the model's native thinking mode.

        deepseek_r1      -- no extra kwargs (thinking appears as <think> tags in content)
        qwen_thinking    -- extra_body={"enable_thinking": True}  (Dashscope endpoint)
        openai_reasoning -- reasoning_effort="high"  (temperature must be omitted)
        """
        if self._reasoning_style == "qwen_thinking":
            return {"extra_body": {"enable_thinking": True}}
        if self._reasoning_style == "openai_reasoning":
            return {"reasoning_effort": "high"}
        return {}

    def _extract_thinking(self, text: str) -> tuple[str | None, str]:
        """Strip <think>...</think> block from text.

        Returns:
            (thinking_content, clean_text)  -- thinking is None if no block found.
        """
        match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
        if match:
            thinking = match.group(1).strip() or None
            clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            return thinking, clean
        return None, text

    def _chat_text(self, messages: list[dict], temperature: float) -> LLMResponse:
        """Simple text chat without tools."""
        extra = self._reasoning_extra_kwargs()
        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )
        # o1/o3/o4 do not accept temperature
        if self._reasoning_style != "openai_reasoning":
            kwargs["temperature"] = temperature
        kwargs.update(extra)

        response = self._create_completion(**kwargs)
        self._track_tokens(response)

        msg = response.choices[0].message
        text = msg.content or ""
        thinking: str | None = None

        if self._reasoning_style in ("qwen_thinking", "deepseek_thinking"):
            # Dashscope/DeepSeek-V4 return thinking in reasoning_content field
            thinking = getattr(msg, "reasoning_content", None) or None
        elif self._reasoning_style == "deepseek_r1":
            thinking, text = self._extract_thinking(text)

        return LLMResponse(text=text, thinking=thinking)

    def _chat_with_tools(
        self, messages: list[dict], tools: list[dict], temperature: float
    ) -> LLMResponse:
        """Chat using native function calling."""
        try:
            extra = self._reasoning_extra_kwargs()
            kwargs: dict = dict(
                model=self.model,
                messages=messages,
                tools=tools,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
            if self._reasoning_style != "openai_reasoning":
                kwargs["temperature"] = temperature
            kwargs.update(extra)

            response = self._create_completion(**kwargs)
            self._track_tokens(response)

            msg = response.choices[0].message

            # Extract thinking content
            thinking: str | None = None
            raw_text: str | None = msg.content

            if self._reasoning_style in ("qwen_thinking", "deepseek_thinking"):
                thinking = getattr(msg, "reasoning_content", None) or None
            elif self._reasoning_style == "deepseek_r1" and raw_text:
                thinking, raw_text = self._extract_thinking(raw_text)

            # Check for tool calls
            if msg.tool_calls:
                calls = []
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    calls.append(ToolCall(
                        name=tc.function.name,
                        arguments=args,
                        id=tc.id or "",
                    ))
                return LLMResponse(text=raw_text, tool_calls=calls, thinking=thinking)

            return LLMResponse(text=raw_text or "", thinking=thinking)

        except Exception as e:
            error_msg = str(e).lower()
            # If function calling not supported, fall back
            if "tool" in error_msg or "function" in error_msg or "unsupported" in error_msg:
                logger.warning(f"Function calling failed, falling back to prompt mode: {e}")
                self._supports_fc = False
                return self._chat_with_prompt_tools(messages, tools, temperature)
            raise

    def _chat_with_prompt_tools(
        self, messages: list[dict], tools: list[dict], temperature: float
    ) -> LLMResponse:
        """Fallback: inject tool descriptions into prompt, parse JSON response."""
        tool_desc = self._format_tools_for_prompt(tools)

        # Inject tool descriptions into system message
        augmented = list(messages)
        if augmented and augmented[0]["role"] == "system":
            augmented[0] = {
                "role": "system",
                "content": augmented[0]["content"] + "\n\n" + tool_desc,
            }
        else:
            augmented.insert(0, {"role": "system", "content": tool_desc})

        response = self._create_completion(
            model=self.model,
            messages=augmented,
            temperature=temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )
        self._track_tokens(response)

        text = response.choices[0].message.content or ""
        return self._parse_tool_calls_from_text(text)

    def _format_tools_for_prompt(self, tools: list[dict]) -> str:
        """Format tool schemas as text instructions for prompt-based mode."""
        lines = [
            "## Available Tools",
            "",
            "You can call tools by responding with a JSON block like:",
            '```json',
            '{"tool": "tool_name", "arguments": {"arg1": "value1"}}',
            '```',
            "",
            "If you want to provide a final answer (no more tool calls), respond with plain text WITHOUT any JSON tool block.",
            "",
            "### Tools:",
            "",
        ]
        for tool in tools:
            fn = tool.get("function", tool)
            name = fn.get("name", "unknown")
            desc = fn.get("description", "")
            params = fn.get("parameters", {})
            props = params.get("properties", {})
            required = params.get("required", [])

            lines.append(f"**{name}**: {desc}")
            if props:
                lines.append("  Parameters:")
                for pname, pinfo in props.items():
                    ptype = pinfo.get("type", "any")
                    pdesc = pinfo.get("description", "")
                    req = " (required)" if pname in required else ""
                    lines.append(f"  - {pname} ({ptype}{req}): {pdesc}")
            lines.append("")

        return "\n".join(lines)

    def _parse_tool_calls_from_text(self, text: str) -> LLMResponse:
        """Parse tool calls from text response (prompt-based fallback)."""
        # Look for JSON blocks
        json_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
        matches = re.findall(json_pattern, text, re.DOTALL)

        tool_calls = []
        for match in matches:
            try:
                data = json.loads(match.strip())
                if "tool" in data:
                    tool_calls.append(ToolCall(
                        name=data["tool"],
                        arguments=data.get("arguments", {}),
                        id=f"prompt_{len(tool_calls)}",
                    ))
            except json.JSONDecodeError:
                continue

        if tool_calls:
            # Remove JSON blocks from text for the accompanying message
            clean_text = re.sub(json_pattern, "", text, flags=re.DOTALL).strip()
            return LLMResponse(text=clean_text or None, tool_calls=tool_calls)

        return LLMResponse(text=text)

    def _detect_function_calling(self) -> bool:
        """Try to detect if the model supports function calling."""
        # Known models that support function calling
        fc_models = ["gpt-", "qwen", "deepseek", "glm-"]
        model_lower = self.model.lower()
        for prefix in fc_models:
            if prefix in model_lower:
                return True
        # Ollama models generally don't support FC natively
        if self.base_url and "11434" in self.base_url:
            return False
        # Default: try it
        return True

    def test_connection(self) -> tuple[bool, str]:
        """Send a minimal request to verify API key and connectivity."""
        try:
            self._create_completion(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=5,
                timeout=10,
            )
            return True, ""
        except Exception as e:
            return False, str(e)

    def _track_tokens(self, response):
        """Track token usage from API response, including cached prompt tokens.

        Cache-hit token count is reported with different field names by provider:
        - OpenAI / DashScope(Qwen) compat: usage.prompt_tokens_details.cached_tokens
        - DeepSeek native (api.deepseek.com): usage.prompt_cache_hit_tokens
        We read both so cache stats are captured regardless of endpoint. Providers
        that expose neither report 0.
        """
        if not (hasattr(response, "usage") and response.usage):
            return
        usage = response.usage
        cached = 0
        # OpenAI / DashScope style: nested prompt_tokens_details.cached_tokens
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", 0) or 0
        # DeepSeek native style: top-level prompt_cache_hit_tokens. The OpenAI
        # SDK keeps unknown fields in model_extra (pydantic v2), so check there too.
        if not cached:
            cached = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
        if not cached:
            extra = getattr(usage, "model_extra", None) or {}
            cached = extra.get("prompt_cache_hit_tokens", 0) or 0
        self.tokens.record(
            prompt=usage.prompt_tokens or 0,
            completion=usage.completion_tokens or 0,
            cached=cached,
        )
