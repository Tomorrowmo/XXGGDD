"""
VLM 视觉语言模型 & LLM 调用模块
支持 Qwen2.5-VL-7B（本地 vLLM）流式分析试验数据图表
"""
import base64
import json
from pathlib import Path
from typing import AsyncGenerator
import httpx

# VLM 服务地址
VLM_BASE_URL = "http://localhost:8000/v1"
VLM_MODEL = "Qwen2.5-VL-7B"

# 分析 prompt 模板
SYSTEM_PROMPT = (
    "你是一位资深的航天发动机燃烧试验数据分析专家。"
    "请仔细观察提供的压力-时间曲线和流道压力分布图，从以下角度进行分析：\n"
    "1. 曲线整体趋势是否正常，有无明显的压力突变或振荡\n"
    "2. 点火、稳定燃烧、熄火各阶段的时间划分和特征\n"
    "3. 当量比变化趋势与压力变化的对应关系\n"
    "4. 是否存在疑似异常工况（如燃烧不稳定、提前熄火迹象等）\n"
    "5. 流道沿程压力分布是否合理\n"
    "请用中文回答，条理清晰，给出专业判断。"
)


def _encode_image(image_path: Path) -> str:
    """将图片编码为 base64 data URL"""
    ext = image_path.suffix.lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext.lstrip("."), "image/png")
    data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{data}"


async def analyze_image_stream(
    image_path: Path,
    model: str = None,
    base_url: str = None,
    api_key: str = None,
) -> AsyncGenerator[str, None]:
    """流式调用 VLM 分析图片，支持动态模型配置"""
    from openai import AsyncOpenAI

    image_url = _encode_image(image_path)
    client = AsyncOpenAI(
        api_key=api_key or "none",
        base_url=base_url or VLM_BASE_URL,
    )

    stream = await client.chat.completions.create(
        model=model or VLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": "请分析这张航天发动机试验的压力曲线图。"},
                ],
            },
        ],
        max_tokens=1500,
        temperature=0.3,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


async def chat_stream(
    image_path: Path, messages: list,
    model: str = None, base_url: str = None, api_key: str = None,
) -> AsyncGenerator[str, None]:
    """多轮对话 VLM，支持动态模型配置"""
    from openai import AsyncOpenAI

    image_url = _encode_image(image_path)

    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for i, msg in enumerate(messages):
        if msg["role"] == "user" and i == 0:
            api_messages.append({
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": msg["content"]},
                ],
            })
        elif msg["role"] in ("user", "assistant"):
            api_messages.append({"role": msg["role"], "content": msg["content"]})

    client = AsyncOpenAI(
        api_key=api_key or "none",
        base_url=base_url or VLM_BASE_URL,
    )

    stream = await client.chat.completions.create(
        model=model or VLM_MODEL,
        messages=api_messages,
        max_tokens=1500,
        temperature=0.3,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


# CFD 云图分析专用 prompt
CFD_ANALYSIS_PROMPT = (
    "你是一位资深的计算流体力学（CFD）与航空航天推进系统分析专家。"
    "请仔细观察提供的 CFD 仿真云图，从以下角度进行专业分析：\n"
    "1. 流场整体结构特征（激波系、膨胀波、剪切层、回流区等）\n"
    "2. 关键物理量分布规律（压力、温度、马赫数梯度与极值位置）\n"
    "3. 燃烧组织特征（火焰稳定方式、释热分布、当量比分布合理性）\n"
    "4. 壁面附近流动特征（边界层分离、激波/边界层干扰）\n"
    "5. 潜在的性能优化方向或异常结构\n"
    "请用中文回答，Markdown 格式，条理清晰，给出专业判断。"
)


async def analyze_cfd_image_stream(
    image_path: str,
    model: str = None,
    base_url: str = None,
    api_key: str = None,
) -> AsyncGenerator[str, None]:
    """流式调用 VLM 分析 CFD 云图，支持任意 OpenAI 兼容端点"""
    from openai import AsyncOpenAI

    image_url = _encode_image(Path(image_path))
    client = AsyncOpenAI(
        api_key=api_key or "none",
        base_url=base_url or VLM_BASE_URL,
    )

    stream = await client.chat.completions.create(
        model=model or VLM_MODEL,
        messages=[
            {"role": "system", "content": CFD_ANALYSIS_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": "请分析这张 CFD 仿真云图，给出专业的流动与燃烧诊断意见。"},
                ],
            },
        ],
        max_tokens=1500,
        temperature=0.3,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content
