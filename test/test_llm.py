"""Tests for hydroagent.llm."""

import pytest

from hydroagent.llm import (
    ToolCall,
    LLMResponse,
    TokenTracker,
    model_profile,
    detect_reasoning_style,
)


class TestModelProfile:
    def test_deepseek_v3_is_dialogue(self):
        profile = model_profile("deepseek-v3.1")
        assert profile["type"] == "dialogue"
        assert profile["temperature"] == 0.3
        assert profile["is_reasoning"] is False

    def test_deepseek_r1_is_reasoning(self):
        profile = model_profile("deepseek-r1")
        assert profile["type"] == "reasoning"
        assert profile["temperature"] == 0.0
        assert profile["is_reasoning"] is True

    def test_qwen_is_dialogue(self):
        profile = model_profile("qwen-plus")
        assert profile["type"] == "dialogue"

    def test_qwq_is_reasoning(self):
        profile = model_profile("qwq-32b")
        assert profile["type"] == "reasoning"
        assert profile["temperature"] == 0.0

    def test_o1_is_reasoning(self):
        profile = model_profile("o1-mini")
        assert profile["type"] == "reasoning"

    def test_gpt4o_is_dialogue(self):
        profile = model_profile("gpt-4o")
        assert profile["type"] == "dialogue"

    def test_claude_is_dialogue(self):
        profile = model_profile("claude-sonnet-4-6")
        assert profile["type"] == "dialogue"

    def test_deepseek_v4_is_unknown(self):
        # "v4" is not in _DIALOGUE_KEYWORDS (only v3, v3.1), so it falls to unknown
        profile = model_profile("deepseek-v4-pro")
        assert profile["type"] == "unknown"
        assert profile["temperature"] == 0.1

    def test_unknown_model_defaults(self):
        profile = model_profile("unknown-model-xyz")
        assert profile["type"] == "unknown"
        assert profile["temperature"] == 0.1
        assert profile["is_reasoning"] is False

    def test_case_insensitive(self):
        profile = model_profile("DEEPSEEK-V3.1")
        assert profile["type"] == "dialogue"


class TestDetectReasoningStyle:
    def test_deepseek_r1_returns_deepseek_r1(self):
        assert detect_reasoning_style("deepseek-r1") == "deepseek_r1"

    def test_deepseek_r2_returns_deepseek_r1(self):
        assert detect_reasoning_style("deepseek-r2-distill-qwen") == "deepseek_r1"

    def test_deepseek_v4_returns_deepseek_thinking(self):
        assert detect_reasoning_style("deepseek-v4-pro") == "deepseek_thinking"

    def test_deepseek_v5_returns_deepseek_thinking(self):
        assert detect_reasoning_style("deepseek-v5-flash") == "deepseek_thinking"

    def test_deepseek_v3_no_thinking(self):
        assert detect_reasoning_style("deepseek-v3.1") is None

    def test_qwq_returns_qwen_thinking(self):
        assert detect_reasoning_style("qwq-32b") == "qwen_thinking"

    def test_qwq_plus_returns_qwen_thinking(self):
        assert detect_reasoning_style("qwq-plus") == "qwen_thinking"

    def test_openai_o1_returns_openai_reasoning(self):
        assert detect_reasoning_style("o1-mini") == "openai_reasoning"

    def test_openai_o3_returns_openai_reasoning(self):
        assert detect_reasoning_style("o3-mini") == "openai_reasoning"

    def test_standard_model_returns_none(self):
        assert detect_reasoning_style("qwen-plus") is None
        assert detect_reasoning_style("gpt-4o") is None


class TestTokenTracker:
    def test_initial_state(self):
        tt = TokenTracker()
        assert tt.total == 0
        assert tt.call_count == 0
        assert tt.total_prompt == 0
        assert tt.total_completion == 0
        assert tt.total_cached == 0
        assert tt.calls == []

    def test_record_single_call(self):
        tt = TokenTracker()
        tt.record(prompt=100, completion=50)
        assert tt.call_count == 1
        assert tt.total_prompt == 100
        assert tt.total_completion == 50
        assert tt.total == 150

    def test_record_multiple_calls(self):
        tt = TokenTracker()
        tt.record(prompt=100, completion=50, cached=20)
        tt.record(prompt=200, completion=80, cached=40)
        assert tt.call_count == 2
        assert tt.total_prompt == 300
        assert tt.total_completion == 130
        assert tt.total == 430
        assert tt.total_cached == 60

    def test_last_call_empty(self):
        tt = TokenTracker()
        assert tt.last_call() == {}

    def test_last_call_latest(self):
        tt = TokenTracker()
        tt.record(prompt=100, completion=50)
        assert tt.last_call() == {"prompt": 100, "completion": 50, "cached": 0}

    def test_reset(self):
        tt = TokenTracker()
        tt.record(prompt=100, completion=50)
        tt.reset()
        assert tt.total == 0
        assert tt.call_count == 0
        assert tt.calls == []

    def test_summary(self):
        tt = TokenTracker()
        tt.record(prompt=100, completion=50, cached=10)
        s = tt.summary()
        assert s == {
            "calls": 1,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "cached_tokens": 10,
            "total_tokens": 150,
        }


class TestToolCall:
    def test_basic(self):
        tc = ToolCall(name="calibrate", arguments={"basin": "01013500"})
        assert tc.name == "calibrate"
        assert tc.arguments == {"basin": "01013500"}

    def test_default_id(self):
        tc = ToolCall(name="test", arguments={})
        assert tc.id == ""

    def test_with_id(self):
        tc = ToolCall(name="test", arguments={}, id="call_123")
        assert tc.id == "call_123"


class TestLLMResponse:
    def test_text_response(self):
        r = LLMResponse(text="hello")
        assert r.is_text()
        assert not r.is_tool_call()

    def test_tool_call_response(self):
        r = LLMResponse(tool_calls=[ToolCall(name="f", arguments={})])
        assert r.is_tool_call()
        assert not r.is_text()

    def test_thinking_field(self):
        r = LLMResponse(text="result", thinking="Let me think...")
        assert r.thinking == "Let me think..."

    def test_default_thinking_none(self):
        r = LLMResponse(text="result")
        assert r.thinking is None
