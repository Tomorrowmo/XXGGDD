"""
DeepSeek LLM 调用模块
使用 OpenAI SDK + DeepSeek 官方调用方式
"""
import os
from typing import AsyncGenerator
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

_client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

SYSTEM_PROMPT = """你是一位资深的航天发动机燃烧试验数据分析专家。
请对以下热试车压力数据进行诊断分析。

## 重要说明
- 所有压力值已经加过大气压修正（+0.101325 MPa），因此正常工况下压力不可能小于 0
- 发动机工作状态下压力在 0.00001 ~ 10 MPa 之间均为正常范围，不要将其标记为异常

## 自动校验规则（严格执行以下阈值）
- 压力最小值 < 0 → 严重异常：数据已加过大气压修正，负压意味着传感器故障或数据采集错误
- 压力最大值 > 10 MPa → 超出常规工作压力范围，需关注
- 标准差 > 均值 × 2 且均值 > 0.01 → 该通道压力波动异常剧烈，可能存在传感器噪声或真实物理振荡

## 输出要求
1. 首先列出发现的所有异常通道及具体数值
2. 然后给出整体诊断结论（数据质量评估、可能的传感器问题、建议关注区域）
3. 最后总结：该次试验数据是否可信，哪些通道数据需要人工复核

请用中文回答，Markdown 格式，条理清晰。"""


async def chat_stream(
    messages: list,
    model: str = None,
    temperature: float = 0.3,
    max_tokens: int = 8192,
) -> AsyncGenerator[str, None]:
    """
    流式调用 DeepSeek API，逐 token 返回

    messages 格式：[{"role": "user", "content": "..."}, ...]
    """
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "sk-your-api-key-here":
        yield "错误：请在 .env 文件中配置 DEEPSEEK_API_KEY"
        return

    try:
        stream = await _client.chat.completions.create(
            model=model or DEEPSEEK_MODEL,
            messages=[{"role": m["role"], "content": m["content"]} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
    except Exception as e:
        yield f"API 调用失败：{str(e)}"


def _build_validation_summary(stats_list: list) -> str:
    """构建自动校验 + 统计摘要文本"""
    alerts = []
    total = len(stats_list)
    neg_warnings = 0
    high_warnings = 0
    std_warnings = 0

    for s in stats_list:
        if s["min"] < 0:
            neg_warnings += 1
            alerts.append(f"🚨 {s['label']}：最小值 {s['min']:.4f} MPa（< 0，已加过大气压修正，负压为严重异常）")
        if s["max"] > 10.0:
            high_warnings += 1
            alerts.append(f"⚠️ {s['label']}：最大值 {s['max']:.4f} MPa（> 10 MPa，超出常规范围）")
        if s["std"] > s["mean"] * 2 and s["mean"] > 0.01:
            std_warnings += 1
            alerts.append(f"⚠️ {s['label']}：标准差 {s['std']:.4f} > 均值×2（波动异常剧烈）")

    summary_lines = [
        f"数据文件包含 {total} 个流道压力通道。",
        f"自动校验发现：负压异常 {neg_warnings} 个、超限 {high_warnings} 个、波动异常 {std_warnings} 个。",
        f"注：压力 0.00001~10 MPa 为正常工作范围，数据已加过大气压修正（+0.101325 MPa）。",
    ]
    if alerts:
        summary_lines.append("\n异常详情：")
        summary_lines.extend(alerts[:30])
    else:
        summary_lines.append("\n未发现明显异常。")

    summary_lines.append("\n通道统计摘要（单位 MPa）：")
    summary_lines.append("| 通道 | 均值 | 最小值 | 最大值 | 标准差 |")
    summary_lines.append("|------|------|--------|--------|--------|")
    for s in stats_list[:30]:
        summary_lines.append(f"| {s['label']} | {s['mean']:.4f} | {s['min']:.4f} | {s['max']:.4f} | {s['std']:.4f} |")
    if total > 30:
        summary_lines.append(f"| ... | ... | ... | ... | ... |")
        for s in stats_list[-5:]:
            summary_lines.append(f"| {s['label']} | {s['mean']:.4f} | {s['min']:.4f} | {s['max']:.4f} | {s['std']:.4f} |")

    return "\n".join(summary_lines)


async def diagnose_data(
    stats_list: list,
    chat_history: list = None,
) -> AsyncGenerator[str, None]:
    """
    基于流道统计数据进行自动校验 + 智能诊断，流式返回

    stats_list  : 统计结果列表
    chat_history: 可选，之前的对话历史 [{"role": "user", "content": "..."}, ...]
                  首次调用为 None，后续追问时传入
    """
    summary = _build_validation_summary(stats_list)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if chat_history and len(chat_history) > 0:
        # 有历史：先附上数据摘要，再追加历史对话
        messages.append({"role": "user", "content": f"以下是本次试验的数据摘要：\n\n{summary}"})
        # 只保留最近 5 轮=10条
        recent = chat_history[-10:] if len(chat_history) > 10 else chat_history
        messages.extend(recent)
    else:
        # 首次诊断
        messages.append({"role": "user", "content": summary})

    async for token in chat_stream(messages, temperature=0.3, max_tokens=8192):
        yield token
