"""DeepSeek 缓存命中小测。

用途：切换到 DeepSeek 后，验证我们能否正确捕获 prompt cache 命中 token。
设计：用一段较长的 system prompt 连发两次相同请求。DeepSeek 默认开启硬盘
前缀缓存，第二次请求应命中缓存，usage 里出现 prompt_cache_hit_tokens > 0。

运行：
    PYTHONUTF8=1 .venv/Scripts/python.exe experiment/test_deepseek_cache.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from hydroagent.config import load_config
from hydroagent.llm import LLMClient


# 较长的 system prompt（>64 token，保证可被缓存）
LONG_SYSTEM = (
    "你是一个水文模型率定助手。以下是 GR4J 模型四个参数的物理含义，请牢记：\n"
    "x1 (产流水库最大容量, mm): 控制流域蓄水能力，值越大基流越稳定，典型范围 100-1200。\n"
    "x2 (地下水交换系数): 正值表示流域向外补给，负值表示流域接受外部补给，范围 -5 到 3。\n"
    "x3 (汇流水库容量, mm): 控制退水快慢，值越大退水越缓，典型范围 20-300。\n"
    "x4 (单位线时间基数, 天): 控制洪峰滞后，与流域汇流时间相关，范围 0.5-4。\n"
    "率定时若某参数贴近边界，说明先验范围设置不当，应根据流域气候属性调整。\n"
    "湿润流域 x1 通常偏大；半干旱流域 x1 偏小、x2 偏负。\n"
    "评估指标 NSE 衡量整体拟合，KGE 拆解相关性/偏差/变率，FHV/FLV 看高低流量段偏差。\n"
)

MESSAGES = [
    {"role": "system", "content": LONG_SYSTEM},
    {"role": "user", "content": "请用一句话总结 x1 参数的物理含义。"},
]


def _dump_usage(label, resp):
    usage = getattr(resp, "usage", None)
    if usage is None:
        print(f"[{label}] 无 usage 字段")
        return
    print(f"[{label}] prompt={getattr(usage,'prompt_tokens',None)} "
          f"completion={getattr(usage,'completion_tokens',None)}")
    # OpenAI/DashScope 风格
    details = getattr(usage, "prompt_tokens_details", None)
    print(f"    prompt_tokens_details.cached_tokens = "
          f"{getattr(details, 'cached_tokens', None) if details else None}")
    # DeepSeek 原生风格
    print(f"    usage.prompt_cache_hit_tokens  = {getattr(usage, 'prompt_cache_hit_tokens', None)}")
    print(f"    usage.prompt_cache_miss_tokens = {getattr(usage, 'prompt_cache_miss_tokens', None)}")
    extra = getattr(usage, "model_extra", None) or {}
    if extra:
        print(f"    model_extra keys = {list(extra.keys())}")


def main():
    cfg = load_config()
    client = LLMClient(cfg["llm"])
    print(f"=== provider: model={client.model}, base_url={cfg['llm'].get('base_url')} ===\n")

    # --- 直接 raw 调用两次，打印原始 usage 证明字段位置 ---
    print(">>> 第 1 次 raw 调用（预期全 miss）")
    r1 = client.client.chat.completions.create(model=client.model, messages=MESSAGES, temperature=0)
    _dump_usage("raw#1", r1)

    print("\n>>> 第 2 次 raw 调用（相同 prefix，预期命中缓存）")
    r2 = client.client.chat.completions.create(model=client.model, messages=MESSAGES, temperature=0)
    _dump_usage("raw#2", r2)

    # --- 走我们自己的 chat() + TokenTracker，验证提取逻辑 ---
    print("\n>>> 通过 LLMClient.chat() + TokenTracker（验证我们的代码能否抓到）")
    client.tokens.reset() if hasattr(client.tokens, "reset") else None
    client.chat(MESSAGES)
    client.chat(MESSAGES)
    summ = client.tokens.summary()
    print(f"    TokenTracker.summary() = {summ}")
    cached = summ.get("cached_tokens", 0)
    print("\n=== 结论 ===")
    if cached and cached > 0:
        print(f"OK: 成功捕获缓存命中 cached_tokens={cached}")
    else:
        print("WARN: cached_tokens=0 —— 检查 raw usage 输出确认 DeepSeek 是否返回了缓存字段，"
              "或前缀过短/缓存未注册。")


if __name__ == "__main__":
    main()
