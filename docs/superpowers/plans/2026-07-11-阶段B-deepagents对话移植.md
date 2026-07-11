# 阶段 B：deepagents 对话内核移植 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 mirror-cortex 的 deepagents 对话能力（agent 循环 + skills + 工具可视化 + markdown/mermaid/图片内联）移植进本项目，就地替换 RAGflow"通用对话"子标签，用可选模型（DeepSeek 默认）驱动。

**Architecture:** 后端新增 `app/agent_runtime/`（去 Flask 化的 agent 构建 + SSE 翻译 + 系统提示 + 单例锁）与 `POST /api/agent/chat`（同步生成器 + StreamingResponse，Starlette 线程池执行 deepagents 同步 stream）。前端移植 `chat_render.js`、新写 `agent_chat.js`、新增 mermaid 渲染、第三方库本地 vendor 化。单会话内存态：前端传完整 messages，后端不落库。

**Tech Stack:** FastAPI、deepagents 0.6.9、langgraph 1.2.5、langchain 1.3.9 / core 1.4.7 / openai 1.3.1（DeepSeek via ChatOpenAI）、pytest、原生 JS + marked/DOMPurify/highlight.js/mermaid。

**前置条件:** 阶段 A 已完成（`app/` 包结构、`app/config.py`、`app/main.py` 已就位）。

## Global Constraints

- 依赖严格锁版本：`deepagents==0.6.9`、`langgraph==1.2.5`、`langchain==1.3.9`、`langchain-core==1.4.7`、`langchain-openai==1.3.1`。
- 单会话内存态：后端不持久化对话；前端每次请求传完整 `messages`；无用户系统、无数据库、无作业管理、无 3D 预览。
- SSE 事件协议（与 mirror-cortex 一致，不改）：`token` / `tool_call` / `tool_result` / `error` / `done`。
- agent 文件产物写虚拟路径 `/workspace`（映射真实 `WORKSPACE_DIR`）；backend 根 = 项目根（供 SkillsMiddleware 读 `skills/`）。
- 第三方前端库全部本地化到 `static/vendor/`，不引用外网 CDN。
- DeepSeek 默认：`model_name=deepseek-v4-flash`、`api_base=https://api.deepseek.com`、`context_window=1M`、`api_key=sk-17d30467aac14bfebfae60696c6e00d4`（可被环境变量 `DEEPSEEK_API_KEY` 覆盖）。
- 工作目录：所有命令在项目根执行。
- 提交信息中文，`[新增]`/`[优化]` 前缀，无 AI 署名。

---

## File Structure

- Modify: `requirements.txt` — 追加 deepagents 全套 + pytest
- Create: `app/agent_runtime/__init__.py`
- Create: `app/agent_runtime/config.py` — 模型配置读取 + token 数解析
- Create: `app/agent_runtime/sse.py` — StreamTranslator（移植）
- Create: `app/agent_runtime/prompt.py` — skills 扫描 + 系统提示（精简移植）
- Create: `app/agent_runtime/agent.py` — backend + middleware + build_agent（去 Flask 移植）
- Create: `app/agent_runtime/manager.py` — 单例 agent 缓存 + 生成锁
- Create: `app/routers/agent_chat.py` — `POST /api/agent/chat`、`GET /api/agent/models`
- Modify: `app/main.py` — mount `/workspace`、include agent_chat router
- Modify: `models.json` — 追加 DeepSeek agent 条目
- Create: `skills/data-plot/SKILL.md` + `skills/data-plot/scripts/plot_csv.py` — 最小示例 skill
- Create: `workspace/.gitkeep`
- Create: `tests/test_agent_config.py`、`tests/test_sse_translator.py`、`tests/test_prompt_skills.py`
- Download: `static/vendor/marked.min.js`、`purify.min.js`、`highlight.min.js`、`github-dark.min.css`、`mermaid.min.js`
- Create: `static/js/chat_render.js`（移植 + mermaid）
- Create: `static/js/agent_chat.js`
- Create: `static/css/agent_chat.css`
- Modify: `static/index.html` — 引入 vendor 脚本 + chat_render.js + agent_chat.js
- Modify: `static/tabs/ragflow.html` — 替换"通用对话"子标签内容

---

## Task B0: 安装依赖 + 下载前端 vendor 库

**Files:**
- Modify: `requirements.txt`
- Download: `static/vendor/*`

**Interfaces:**
- Produces: 可 import 的 `deepagents`、`langchain_openai`、`langgraph`；`static/vendor/` 下 5 个库文件。

- [ ] **Step 1: 追加依赖到 requirements.txt**

在 `requirements.txt` 末尾追加：
```
# —— agent 对话（阶段B，锁版本对齐 mirror-cortex）——
deepagents==0.6.9
langgraph==1.2.5
langchain==1.3.9
langchain-core==1.4.7
langchain-openai==1.3.1
pytest>=8,<9
```

- [ ] **Step 2: 安装并验证 import（可能与现有包冲突，冲突则记录）**

Run（在项目根、conda gy_pytorch 环境）：
```bash
pip install "deepagents==0.6.9" "langgraph==1.2.5" "langchain==1.3.9" "langchain-core==1.4.7" "langchain-openai==1.3.1" "pytest>=8,<9"
python -c "import deepagents, langgraph, langchain, langchain_openai; from deepagents import create_deep_agent; from deepagents.backends import LocalShellBackend; print('deepagents import OK')"
```
Expected: `deepagents import OK`。若报依赖冲突（如 pydantic/openai 版本），记录冲突包与版本到本任务备注，优先按 deepagents 要求调整；无法调和时改用独立 venv 并在 `run.py` 注释说明。

- [ ] **Step 3: 下载前端第三方库到 vendor（在有外网的机器执行，产物提交入库）**

Run（在项目根）：
```bash
mkdir -p static/vendor
curl -fsSL https://cdn.jsdelivr.net/npm/marked@12/marked.min.js -o static/vendor/marked.min.js
curl -fsSL https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js -o static/vendor/purify.min.js
curl -fsSL https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js -o static/vendor/highlight.min.js
curl -fsSL https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/github-dark.min.css -o static/vendor/github-dark.min.css
curl -fsSL https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js -o static/vendor/mermaid.min.js
```

- [ ] **Step 4: 校验 vendor 文件非空**

Run:
```bash
for f in marked.min.js purify.min.js highlight.min.js github-dark.min.css mermaid.min.js; do
  sz=$(wc -c < static/vendor/$f); echo "$f: $sz bytes"; [ "$sz" -gt 1000 ] || echo "  !! $f 过小，下载可能失败";
done
```
Expected: 每个文件 > 1000 bytes，无 `!!` 告警。

- [ ] **Step 5: 提交**

```bash
git add requirements.txt static/vendor/
git commit -m "[新增] 引入 deepagents 依赖与前端 vendor 库（marked/dompurify/highlight/mermaid）"
```

---

## Task B1: agent_runtime/config.py — 模型配置读取

**Files:**
- Create: `app/agent_runtime/__init__.py`（空）
- Create: `app/agent_runtime/config.py`
- Test: `tests/test_agent_config.py`

**Interfaces:**
- Produces:
  - `parse_token_count(v, default=1_000_000) -> int`
  - `load_models() -> list[dict]`
  - `get_agent_model(model_id: str | None) -> dict`，返回 `{"model": str, "base_url": str, "api_key": str, "context_window": int}`
  - 常量 `DEFAULT_MODEL_ID = "deepseek/agent"`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_agent_config.py`：
```python
from app.agent_runtime.config import parse_token_count

def test_parse_token_count_suffixes():
    assert parse_token_count("1M") == 1_000_000
    assert parse_token_count("256K") == 256_000
    assert parse_token_count(200000) == 200000
    assert parse_token_count(None, default=123) == 123
    assert parse_token_count("garbage", default=999) == 999
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_agent_config.py -v`
Expected: FAIL（`ModuleNotFoundError: app.agent_runtime.config`）。

- [ ] **Step 3: 实现 config.py**

创建 `app/agent_runtime/__init__.py`（空）。创建 `app/agent_runtime/config.py`：
```python
"""agent 对话模型配置：从 models.json 读取选中模型，DeepSeek 为默认。"""
import json
import os

from app.config import ROOT

MODELS_JSON = ROOT / "models.json"
DEFAULT_MODEL_ID = "deepseek/agent"


def parse_token_count(v, default=1_000_000):
    """解析上下文窗口：支持 '1M' / '256K' / 整数 / None。无法解析回退 default。"""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().upper()
    try:
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        return int(float(s))
    except ValueError:
        return default


def load_models():
    """读取 models.json 的 models 列表。"""
    with open(MODELS_JSON, encoding="utf-8") as f:
        return json.load(f).get("models", [])


def get_agent_model(model_id=None):
    """按 model_id 取模型配置；缺省或未找到回退 DeepSeek 默认。

    api_key 取值优先级：条目 api_key > 条目 api_key_env 指向的环境变量 > DEEPSEEK_API_KEY。
    """
    models = load_models()
    mid = model_id or DEFAULT_MODEL_ID
    cfg = next((m for m in models if m.get("id") == mid), None)
    if cfg is None:
        cfg = next((m for m in models if m.get("id") == DEFAULT_MODEL_ID), None)
    if cfg is None:
        raise ValueError(f"未找到 agent 模型: {mid}（且无默认 {DEFAULT_MODEL_ID}）")
    api_key = cfg.get("api_key") or ""
    if not api_key and cfg.get("api_key_env"):
        api_key = os.getenv(cfg["api_key_env"], "")
    if not api_key:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
    return {
        "model": cfg["model_name"],
        "base_url": cfg["api_base"],
        "api_key": api_key,
        "context_window": parse_token_count(cfg.get("context_window")),
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_agent_config.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add app/agent_runtime/__init__.py app/agent_runtime/config.py tests/test_agent_config.py
git commit -m "[新增] agent_runtime.config 模型配置读取与 token 数解析"
```

---

## Task B2: agent_runtime/sse.py — StreamTranslator（移植）

**Files:**
- Create: `app/agent_runtime/sse.py`
- Test: `tests/test_sse_translator.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `_sse(obj: dict) -> str`（返回 `"data: {json}\n\n"`）
  - `StreamTranslator(skip_count=0)`，方法 `on_messages(chunk, meta=None) -> list[dict]`、`on_values(state: dict) -> list[dict]`
  - 常量 `OUTPUT_LIMIT = 2000`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_sse_translator.py`：
```python
import json
from app.agent_runtime.sse import _sse, StreamTranslator, OUTPUT_LIMIT


def test_sse_format():
    s = _sse({"type": "token", "text": "你好"})
    assert s.startswith("data: ") and s.endswith("\n\n")
    assert json.loads(s[6:].strip()) == {"type": "token", "text": "你好"}


class _FakeToolMsg:
    """伪造 ToolMessage：类名含 ToolMessage，供 on_values 分支识别。"""
    __name__ = "ToolMessage"
    def __init__(self, mid, content, tool_call_id, status="success"):
        self.id = mid; self.content = content
        self.tool_call_id = tool_call_id; self.status = status


# 用真实类名让 type(m).__name__ 命中
class ToolMessage(_FakeToolMsg):
    pass


def test_on_values_skips_input_and_emits_tool_result():
    t = StreamTranslator(skip_count=1)
    msgs = [
        ToolMessage("m0", "被跳过", "tc0"),   # 属于输入区（skip）
        ToolMessage("m1", "结果内容", "tc1"),  # 新增 → 应产出 tool_result
    ]
    out = t.on_values({"messages": msgs})
    assert out == [{"type": "tool_result", "id": "tc1", "output": "结果内容", "ok": True}]


def test_on_values_truncates_long_output():
    t = StreamTranslator(skip_count=0)
    long = "x" * (OUTPUT_LIMIT + 50)
    out = t.on_values({"messages": [ToolMessage("m1", long, "tc1")]})
    assert out[0]["output"].endswith("…（已截断）")
    assert len(out[0]["output"]) == OUTPUT_LIMIT + len("…（已截断）")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_sse_translator.py -v`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 移植 sse.py**

创建 `app/agent_runtime/sse.py`，内容为 mirror-cortex `app/agent_runtime/sse.py` 的**逐字复制**（该文件纯逻辑、无 Flask 依赖）。完整内容：
```python
"""SSE 工具：把 agent.stream 事件翻译成前端 SSE 协议事件。"""
import json

OUTPUT_LIMIT = 2000  # 工具输出 SSE 推送截断字符数


def _sse(obj):
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


class StreamTranslator:
    """把 agent.stream 的事件翻译成前端 SSE 协议事件（纯逻辑，可单测）。"""

    def __init__(self, skip_count=0):
        self._skip = int(skip_count)
        self._seen = set()

    def on_messages(self, chunk, meta=None):
        if meta and meta.get("lc_source") == "summarization":
            return []
        if "AIMessage" not in type(chunk).__name__:
            return []
        content = getattr(chunk, "content", "")
        if isinstance(content, str) and content:
            return [{"type": "token", "text": content}]
        return []

    def on_values(self, state):
        events = []
        for m in state.get("messages", [])[self._skip:]:
            mid = getattr(m, "id", None)
            if mid is not None and mid in self._seen:
                continue
            if mid is not None:
                self._seen.add(mid)
            name = type(m).__name__
            if "ToolMessage" in name:
                content = m.content if isinstance(m.content, str) else str(m.content)
                if len(content) > OUTPUT_LIMIT:
                    content = content[:OUTPUT_LIMIT] + "…（已截断）"
                ok = getattr(m, "status", "success") != "error"
                events.append({"type": "tool_result", "id": m.tool_call_id,
                               "output": content, "ok": ok})
            elif "AIMessage" in name:
                for tc in (getattr(m, "tool_calls", None) or []):
                    events.append({"type": "tool_call", "id": tc["id"],
                                   "name": tc["name"], "args": tc["args"]})
        return events
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_sse_translator.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: 提交**

```bash
git add app/agent_runtime/sse.py tests/test_sse_translator.py
git commit -m "[新增] 移植 StreamTranslator SSE 事件翻译器"
```

---

## Task B3: agent_runtime/prompt.py — skills 扫描 + 系统提示

**Files:**
- Create: `app/agent_runtime/prompt.py`
- Test: `tests/test_prompt_skills.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `skills_overview(skills_dir) -> str`（每行 `- name：description`）
  - `build_system_prompt(skills_dir, workspace_vpath="/workspace") -> str`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_prompt_skills.py`：
```python
from pathlib import Path
from app.agent_runtime.prompt import skills_overview, build_system_prompt


def test_skills_overview_parses_frontmatter(tmp_path):
    sk = tmp_path / "demo" / "SKILL.md"
    sk.parent.mkdir(parents=True)
    sk.write_text("---\nname: demo\ndescription: 演示技能\n---\n# body\n", encoding="utf-8")
    out = skills_overview(str(tmp_path))
    assert out == "- demo：演示技能"


def test_build_system_prompt_contains_workspace_and_skills(tmp_path):
    sk = tmp_path / "demo" / "SKILL.md"
    sk.parent.mkdir(parents=True)
    sk.write_text("---\nname: demo\ndescription: 演示\n---\n", encoding="utf-8")
    p = build_system_prompt(str(tmp_path), workspace_vpath="/workspace")
    assert "/workspace" in p
    assert "demo" in p
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_prompt_skills.py -v`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 prompt.py（精简移植，去用户/作业相关内容）**

创建 `app/agent_runtime/prompt.py`：
```python
"""Agent 系统提示：skills 清单扫描 + 行为约定（精简自 mirror-cortex，去用户/作业逻辑）。"""
import platform
import sys
from pathlib import Path


def skills_overview(skills_dir):
    """扫描 skills/*/SKILL.md 的 YAML frontmatter，生成 'name：description' 清单。"""
    items = []
    for sk in sorted(Path(skills_dir).glob("*/SKILL.md")):
        name = desc = ""
        in_fm = False
        for line in sk.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if s == "---":
                if in_fm:
                    break
                in_fm = True
                continue
            if in_fm and s.startswith("name:"):
                name = s[5:].strip()
            elif in_fm and s.startswith("description:"):
                desc = s[12:].strip()
        if name:
            items.append(f"- {name}：{desc}")
    return "\n".join(items)


def build_system_prompt(skills_dir, workspace_vpath="/workspace"):
    """构建注入 agent 的系统提示。单会话、单用户、产物落 workspace 虚拟路径。"""
    exe = sys.executable
    overview = skills_overview(skills_dir)
    os_name = platform.system()
    if os_name == "Windows":
        shell_desc = "Windows 命令行 cmd.exe"
        os_cmd_hint = ("- 当前是 Windows，shell 没有 ls/cat/rm 等 Unix 命令，"
                       "改用 dir/type/del，或优先用文件工具。\n")
    else:
        shell_desc = "POSIX shell (bash/sh)"
        os_cmd_hint = "- 当前是类 Unix 系统，shell 用 bash/sh 常规命令即可。\n"
    return (
        "你是一个数据分析与仿真助手，运行在本地 Web 服务中。请严格遵守以下约定：\n\n"
        "【运行环境】\n"
        f"本服务运行在 {os_name}。shell 命令经 {shell_desc} 执行。\n"
        f"{os_cmd_hint}"
        "- 列目录/看文件/搜索优先用文件工具（ls/grep/glob/read_file，走虚拟路径）。\n\n"
        "【可用 skills】\n"
        f"skills 加载目录：{skills_dir}\n"
        "下方 Skills System 已列出全部可用 skill 及 SKILL.md 路径，需要时用 read_file 读取对应 "
        "SKILL.md 即可，不要用 ls/dir 遍历 skills 目录。当前可用：\n"
        f"{overview}\n\n"
        "【Python 解释器】\n"
        f"执行 Python 脚本时用：{exe}\n"
        f'即 `"{exe}" 脚本.py`，不要用裸 python/python3。\n\n'
        "【路径规则（区分两类路径）】\n"
        f"1) 文件工具（write_file/read_file/edit_file/ls/grep/glob）用虚拟路径：workspace 是 "
        f"`{workspace_vpath}`（如 `{workspace_vpath}/result.png`）。不要给文件工具传绝对路径。\n"
        "2) shell 命令 / 脚本参数用真实磁盘路径或相对项目根的路径。不要把 `/workspace/...` 这类虚拟"
        "路径当作 shell 参数（会被当成盘符根）。\n"
        "- 你产出的交付文件放 workspace；临时脚本写 workspace，用完默认删除。\n\n"
        "【给用户展示产物】\n"
        f"- 内联展示图片：`![描述]({workspace_vpath}/<文件名>.png)`（文件名用英文、不带空格）。\n"
        f"- 提供下载链接：`[文件名]({workspace_vpath}/<文件名>)`。\n\n"
        "【工作准则】\n"
        "- skills 目录只读：严禁修改 skills/ 下任何文件，只能 read_file 读取。\n"
        "- 不臆测：涉及文件/计算结果时先 read_file 看实际内容再下结论。\n"
        "- 先核实再报成功：确认返回码正常、预期产物已生成，再说完成；失败如实说明并附关键日志。\n"
        "- 参数不清先问：工况/参数缺失或有多种理解时先列出询问；提问后停下等用户回答，不要自问自答。\n"
        "- 多步任务用 write_todos 列计划并随进度更新。\n"
        "- 不死磕：同一问题反复写代码调试最多 5 轮，仍不行就停下如实说明并给用户选项。\n"
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_prompt_skills.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add app/agent_runtime/prompt.py tests/test_prompt_skills.py
git commit -m "[新增] 移植并精简 agent 系统提示与 skills 扫描"
```

---

## Task B4: agent_runtime/agent.py — backend + middleware + build_agent

**Files:**
- Create: `app/agent_runtime/agent.py`

**Interfaces:**
- Consumes: `app.agent_runtime.prompt.build_system_prompt`
- Produces: `build_agent(model_cfg: dict, base_dir: Path, skills_dir: Path, system_prompt: str) -> deep_agent`；类 `RobustLocalShellBackend`、`StripImageBlocksMiddleware`

- [ ] **Step 1: 移植 agent.py（去 Flask）**

创建 `app/agent_runtime/agent.py`。`RobustLocalShellBackend`、`_smart_decode`、`_dangerous_scan`、`_strip_nontext_blocks`、`StripImageBlocksMiddleware` 全部**逐字复制**自 mirror-cortex `app/agent_runtime/agent.py`（第 20-160 行，不含 flask import）。仅 `build_agent` 改为显式传参版本：
```python
"""基于 deepagents 的对话 Agent（去 Flask 移植）。RobustLocalShellBackend / 中间件逐字保留。"""
import re
import subprocess
from pathlib import Path

from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse
from langchain.agents.middleware.types import AgentMiddleware

_DRIVE_ROOT = re.compile(r"^[A-Za-z]:\\[^\\]*$")
_HINT = ("请改用受限搜索：在项目目录下用 `where /r . <文件名>` 或 `dir /s /b <文件名>`"
         "（不带盘符根），或直接向用户索取该文件的完整路径。")

# —— 以下 _smart_decode / _dangerous_scan / RobustLocalShellBackend /
#    _IMG_PLACEHOLDER / _strip_nontext_blocks / StripImageBlocksMiddleware
#    逐字复制 mirror-cortex agent.py 第 27-160 行 ——
# （复制时保持函数体与类完全一致，不做逻辑改动）
```
把 mirror-cortex 第 27-160 行原样粘贴到上面注释处。然后追加改造后的 `build_agent`：
```python
def build_agent(model_cfg, base_dir, skills_dir, system_prompt):
    """构建 agent。

    model_cfg：来自 agent_runtime.config.get_agent_model() 的 dict
      （model / base_url / api_key / context_window）。
    base_dir：backend 根 = 项目根（供 SkillsMiddleware 读 skills 全文）。
    skills_dir：项目根/skills，只读。
    """
    base_dir = Path(base_dir)
    skills_dir = Path(skills_dir)
    model = ChatOpenAI(
        model=model_cfg["model"],
        base_url=model_cfg["base_url"],
        api_key=model_cfg["api_key"],
        temperature=0,
        profile={"max_input_tokens": model_cfg["context_window"]},
    )
    backend = RobustLocalShellBackend(
        root_dir=str(base_dir),
        virtual_mode=True,
        inherit_env=True,
        timeout=1800,
    )
    backend._skills_dir = skills_dir.resolve()
    try:
        skills_vpath = "/" + skills_dir.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        skills_vpath = "/skills"
    return create_deep_agent(model=model, backend=backend,
                             skills=[skills_vpath],
                             system_prompt=system_prompt,
                             middleware=[StripImageBlocksMiddleware()])
```

- [ ] **Step 2: 导入冒烟（不触发真实 LLM 调用）**

Run:
```bash
python -c "from app.agent_runtime.agent import build_agent, RobustLocalShellBackend, StripImageBlocksMiddleware; print('agent module OK')"
```
Expected: `agent module OK`。

- [ ] **Step 3: 确认无残留 flask 引用**

Run:
```bash
grep -n "flask\|current_app" app/agent_runtime/agent.py || echo "无 flask 依赖"
```
Expected: `无 flask 依赖`。

- [ ] **Step 4: 提交**

```bash
git add app/agent_runtime/agent.py
git commit -m "[新增] 移植 deepagents build_agent 与容错 shell backend（去 Flask）"
```

---

## Task B5: agent_runtime/manager.py — 单例缓存 + 生成锁

**Files:**
- Create: `app/agent_runtime/manager.py`

**Interfaces:**
- Consumes: `build_agent`、`build_system_prompt`、`app.config`
- Produces:
  - `get_lock() -> threading.Lock`（进程级唯一生成锁）
  - `get_agent(model_id: str, model_cfg: dict)`（按 model_id 缓存 agent 实例）

- [ ] **Step 1: 实现 manager.py**

创建 `app/agent_runtime/manager.py`：
```python
"""单会话 agent 管理：进程级生成锁 + 按 model_id 缓存 agent 实例。

单用户内部工具：不做按用户隔离，只保证同一时刻只有一轮生成在跑（生成锁）。
"""
import threading

from app.config import ROOT
from app.agent_runtime.agent import build_agent
from app.agent_runtime.prompt import build_system_prompt

SKILLS_DIR = ROOT / "skills"

_lock = threading.Lock()
_agents = {}  # model_id -> agent 实例


def get_lock():
    """返回进程级唯一生成锁（非阻塞 acquire 用于并发保护）。"""
    return _lock


def get_agent(model_id, model_cfg):
    """按 model_id 取缓存的 agent；无则构建并缓存。"""
    if model_id not in _agents:
        system_prompt = build_system_prompt(str(SKILLS_DIR), workspace_vpath="/workspace")
        _agents[model_id] = build_agent(model_cfg, ROOT, SKILLS_DIR, system_prompt)
    return _agents[model_id]
```

- [ ] **Step 2: 导入冒烟**

Run:
```bash
python -c "from app.agent_runtime.manager import get_lock, get_agent; import threading; assert isinstance(get_lock(), type(threading.Lock())); print('manager OK')"
```
Expected: `manager OK`（注：`threading.Lock()` 类型断言若因实现类型不符可放宽为 `get_lock() is not None`）。

- [ ] **Step 3: 提交**

```bash
git add app/agent_runtime/manager.py
git commit -m "[新增] agent_runtime.manager 生成锁与按模型缓存"
```

---

## Task B6: models.json 加 DeepSeek 条目 + skills 示例 + workspace

**Files:**
- Modify: `models.json`
- Create: `skills/data-plot/SKILL.md`
- Create: `skills/data-plot/scripts/plot_csv.py`
- Create: `workspace/.gitkeep`

**Interfaces:**
- Produces: models.json 含 `id="deepseek/agent"` 条目；`skills/data-plot` 可被 skills_overview 扫描；`workspace/` 目录存在。

- [ ] **Step 1: 在 models.json 追加 DeepSeek agent 条目**

打开 `models.json`，在 `models` 数组**首位**插入（provider=local 会置顶，且作为默认）：
```json
{
  "id": "deepseek/agent",
  "name": "DeepSeek (Agent 对话)",
  "provider": "deepseek",
  "api_base": "https://api.deepseek.com",
  "api_key": "sk-17d30467aac14bfebfae60696c6e00d4",
  "api_key_env": "DEEPSEEK_API_KEY",
  "model_name": "deepseek-v4-flash",
  "multimodal": false,
  "max_tokens": 8192,
  "temperature": 0,
  "context_window": "1M",
  "agent_capable": true
}
```

- [ ] **Step 2: 验证 config 能取到默认模型**

Run:
```bash
python -c "from app.agent_runtime.config import get_agent_model; c = get_agent_model(None); assert c['model'] == 'deepseek-v4-flash'; assert c['base_url'] == 'https://api.deepseek.com'; assert c['api_key']; print('agent model:', c['model'], 'ctx:', c['context_window'])"
```
Expected: `agent model: deepseek-v4-flash ctx: 1000000`。

- [ ] **Step 3: 创建最小示例 skill 脚本**

创建 `skills/data-plot/scripts/plot_csv.py`（跨平台纯 Python，读 CSV 首两列画折线，存 PNG）：
```python
"""最小示例 skill：读 CSV 前两列画折线图，输出 PNG 到 workspace。
用法： python plot_csv.py --csv <csv路径> --out <png路径>
"""
import argparse
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    xs, ys = [], []
    with open(args.csv, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    start = 1 if rows and not _is_number(rows[0][0]) else 0
    for r in rows[start:]:
        if len(r) >= 2 and _is_number(r[0]) and _is_number(r[1]):
            xs.append(float(r[0])); ys.append(float(r[1]))

    plt.figure(figsize=(8, 4))
    plt.plot(xs, ys, lw=1.5)
    plt.xlabel("col0"); plt.ylabel("col1"); plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(args.out, dpi=120)
    print(f"OK saved {args.out} ({len(xs)} points)")


def _is_number(s):
    try:
        float(s); return True
    except (ValueError, TypeError):
        return False


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 创建示例 skill 的 SKILL.md**

创建 `skills/data-plot/SKILL.md`：
```markdown
---
name: data-plot
description: 读取 CSV 文件的前两列画折线图并输出 PNG。当用户要"把某个 CSV 画成曲线/折线图"时用。
---

# data-plot · CSV 折线图

## 何时用
用户提供一个 CSV 文件、想快速看某两列的折线趋势时。

## 流程
1. 确认 CSV 的真实磁盘路径（相对项目根，如 `data/xxx.csv`）。
2. 执行脚本（用系统提示指定的 Python 解释器），把图输出到 workspace 的真实磁盘目录 `workspace/`：
   `<python> skills/data-plot/scripts/plot_csv.py --csv <csv路径> --out workspace/<英文名>.png`
3. 脚本打印 `OK saved ...` 即成功。
4. 用 `![结果](/workspace/<英文名>.png)` 把图内联展示给用户。
```

- [ ] **Step 5: 创建 workspace 占位**

创建 `workspace/.gitkeep`（空文件）。

- [ ] **Step 6: 验证 skills 扫描含示例**

Run:
```bash
python -c "from app.agent_runtime.prompt import skills_overview; from app.config import ROOT; print(skills_overview(str(ROOT / 'skills')))"
```
Expected: 输出含 `- data-plot：读取 CSV 文件的前两列画折线图并输出 PNG...`。

- [ ] **Step 7: 提交**

```bash
git add models.json skills/ workspace/.gitkeep
git commit -m "[新增] models.json 加 DeepSeek agent 条目、最小示例 skill data-plot 与 workspace 目录"
```

---

## Task B7: routers/agent_chat.py + main.py 接入

**Files:**
- Create: `app/routers/agent_chat.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `agent_runtime.config.get_agent_model/load_models`、`manager.get_lock/get_agent`、`sse._sse`、`StreamTranslator`
- Produces: `GET /api/agent/models`、`POST /api/agent/chat`（SSE）；`/workspace` 静态挂载。

- [ ] **Step 1: 实现 agent_chat.py**

创建 `app/routers/agent_chat.py`：
```python
"""Agent 对话路由：模型列表 + SSE 流式对话（deepagents 驱动）。

单会话内存态：请求体携带完整 messages（[{role, content}, ...]），后端不落库。
event_stream 为同步生成器 → Starlette 在线程池执行，避免阻塞事件循环
（deepagents 的 agent.stream 是同步阻塞调用）。
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from app.agent_runtime.config import get_agent_model, load_models
from app.agent_runtime.sse import _sse, StreamTranslator
from app.agent_runtime import manager

router = APIRouter()


@router.get("/api/agent/models")
async def agent_models():
    """列出可用于 agent 的模型（agent_capable != False 者），DeepSeek 置顶。"""
    models = load_models()
    out = [{
        "id": m["id"],
        "name": m["name"],
        "default": m["id"] == "deepseek/agent",
    } for m in models if m.get("agent_capable", True) is not False]
    out.sort(key=lambda x: (not x["default"], x["name"]))
    return JSONResponse(out)


@router.post("/api/agent/chat")
def agent_chat(body: dict):
    model_id = (body.get("model_id") or "").strip()
    messages = body.get("messages") or []

    def event_stream():
        lock = manager.get_lock()
        if not lock.acquire(blocking=False):
            yield _sse({"type": "error", "message": "正在生成中，请稍候"})
            return
        try:
            model_cfg = get_agent_model(model_id or None)
            agent = manager.get_agent(model_id or "deepseek/agent", model_cfg)
            lc_msgs = list(messages)
            if not lc_msgs:
                yield _sse({"type": "done"})
                return
            base_count = len(lc_msgs)
            translator = StreamTranslator(skip_count=base_count)
            for mode, payload in agent.stream(
                {"messages": lc_msgs},
                config={"recursion_limit": 2000},
                stream_mode=["values", "messages"],
            ):
                if mode == "messages":
                    chunk, meta = payload
                    out = translator.on_messages(chunk, meta)
                elif mode == "values":
                    out = translator.on_values(payload)
                else:
                    out = []
                for ev in out:
                    yield _sse(ev)
            yield _sse({"type": "done"})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "error", "message": str(exc)})
        finally:
            try:
                lock.release()
            except RuntimeError:
                pass

    return StreamingResponse(
        event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 2: main.py 挂载 workspace + include router**

在 `app/main.py`：
1. import 区加 `from app.config import WORKSPACE_DIR`（若尚未导入）与 `from app.routers import agent_chat as agent_chat_router`。
2. 静态挂载区（其他 `app.mount` 附近）加：
```python
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/workspace", StaticFiles(directory=str(WORKSPACE_DIR)), name="workspace")
```
3. include 区加 `app.include_router(agent_chat_router.router)`。

- [ ] **Step 3: 启动 + 端点冒烟**

Run（项目根）：
```bash
python run.py &
SERVER_PID=$!
sleep 6
curl -s -o /dev/null -w "agentmodels:%{http_code}\n" http://127.0.0.1:8501/api/agent/models
curl -s -o /dev/null -w "agentchat_empty:%{http_code}\n" -X POST http://127.0.0.1:8501/api/agent/chat -H "Content-Type: application/json" -d '{"messages":[]}'
kill $SERVER_PID
```
Expected: `agentmodels:200`、`agentchat_empty:200`（空 messages 直接 done，流式 200）。

- [ ] **Step 4: 真实一轮对话冒烟（需 DeepSeek 可达）**

Run（项目根；验证 token 流与 done）：
```bash
python run.py &
SERVER_PID=$!
sleep 6
curl -s -N -X POST http://127.0.0.1:8501/api/agent/chat -H "Content-Type: application/json" \
  -d '{"model_id":"deepseek/agent","messages":[{"role":"user","content":"用一句话自我介绍"}]}' | head -c 400
echo
kill $SERVER_PID
```
Expected: 输出多条 `data: {"type": "token", ...}`，最后含 `data: {"type": "done"}`。若网络不通/ key 失效，会出现 `data: {"type":"error",...}`——记录并排查 key。

- [ ] **Step 5: 提交**

```bash
git add app/routers/agent_chat.py app/main.py
git commit -m "[新增] agent 对话 SSE 路由与 workspace 静态挂载"
```

---

## Task B8: 前端 chat_render.js 移植 + mermaid 集成

**Files:**
- Create: `static/js/chat_render.js`
- Modify: `static/index.html`

**Interfaces:**
- Consumes: 全局 `marked`、`DOMPurify`、`hljs`、`mermaid`（来自 vendor）
- Produces: `window.ChatRender.create(el)` → `{ addUserBubble, addInfoBubble, newAiBubble, showThinking, removeThinking, appendText, addToolCard, fillToolResult, handleEvent, renderMermaidIn }`

- [ ] **Step 1: 移植 chat_render.js 并新增 mermaid 渲染**

创建 `static/js/chat_render.js`，内容为 mirror-cortex `app/static/js/chat_render.js` 的**逐字复制**，再做两处新增：

(a) 在 `create(chatEl)` 内、`handleEvent` 之前，新增 mermaid 渲染函数：
```javascript
    // 渲染容器内所有未处理的 mermaid 代码块（marked 输出 <code class="language-mermaid">）
    function renderMermaidIn(root) {
      if (typeof mermaid === 'undefined' || !root) return;
      var blocks = root.querySelectorAll('code.language-mermaid');
      blocks.forEach(function (code, i) {
        var pre = code.parentElement;
        if (!pre || pre.dataset.mmDone === '1') return;
        var src = code.textContent || '';
        var id = 'mm-' + Date.now() + '-' + i + '-' + Math.floor(performance.now());
        try {
          mermaid.render(id, src).then(function (res) {
            var wrap = document.createElement('div'); wrap.className = 'mermaid-svg';
            wrap.innerHTML = res.svg;
            pre.replaceWith(wrap);
          }).catch(function () { pre.dataset.mmDone = '1'; });  // 语法错误：保留原始代码块
          pre.dataset.mmDone = '1';
        } catch (e) { pre.dataset.mmDone = '1'; }
      });
    }
```
(b) 在返回对象里加 `renderMermaidIn: renderMermaidIn,`。

说明：流式期间 `appendText` 每 token 重渲染 `innerHTML`，会冲掉已渲染 SVG，故 mermaid **不在 appendText 内触发**，改由 `agent_chat.js` 在 `done` 事件后对该气泡调用一次 `renderMermaidIn(ctx.bubble)`（见 Task B9）。

- [ ] **Step 2: index.html 引入 vendor 脚本与 chat_render.js**

修改 `static/index.html`：
1. `<head>` 内把第 8 行的 CDN marked 换成本地，并补齐 vendor：
```html
<link rel="stylesheet" href="/static/vendor/github-dark.min.css">
<script src="/static/vendor/marked.min.js"></script>
<script src="/static/vendor/purify.min.js"></script>
<script src="/static/vendor/highlight.min.js"></script>
<script src="/static/vendor/mermaid.min.js"></script>
```
（删除原 `https://cdn.jsdelivr.net/npm/marked/marked.min.js` 一行。Plotly 那行是否本地化不在本次范围，保持不变。）
2. 在 `<body>` 底部脚本区、`ragflow.js` **之前**加载渲染器：
```html
<script src="/static/js/chat_render.js"></script>
```
3. 在所有脚本加载后加 mermaid 初始化（紧接 `mermaid.min.js` 或 body 末尾）：
```html
<script>if (typeof mermaid !== 'undefined') mermaid.initialize({ startOnLoad: false, theme: 'dark' });</script>
```

- [ ] **Step 3: 校验加载无控制台报错**

Run（项目根启动后浏览器打开首页，看 Console）：
```bash
python run.py &
SERVER_PID=$!
sleep 6
curl -s -o /dev/null -w "index:%{http_code}\n" http://127.0.0.1:8501/
curl -s -o /dev/null -w "chatrender:%{http_code}\n" http://127.0.0.1:8501/static/js/chat_render.js
curl -s -o /dev/null -w "mermaid:%{http_code}\n" http://127.0.0.1:8501/static/vendor/mermaid.min.js
kill $SERVER_PID
```
Expected: 三者均 `200`。浏览器 Console 无 `ChatRender/mermaid/DOMPurify is not defined` 报错。

- [ ] **Step 4: 提交**

```bash
git add static/js/chat_render.js static/index.html
git commit -m "[新增] 移植 chat_render 气泡渲染器并集成 mermaid，前端库本地化引入"
```

---

## Task B9: 前端 agent_chat.js + ragflow.html 改造 + 样式

**Files:**
- Create: `static/js/agent_chat.js`
- Create: `static/css/agent_chat.css`
- Modify: `static/tabs/ragflow.html`
- Modify: `static/index.html`（引入 agent_chat.js 与 css）

**Interfaces:**
- Consumes: `window.ChatRender`、`POST /api/agent/chat`、`GET /api/agent/models`
- Produces: `window.AgentChat.init()`；替换后的"通用对话"子标签 UI。

- [ ] **Step 1: 改造 ragflow.html 的"通用对话"子标签**

打开 `static/tabs/ragflow.html`，把"💬 通用对话"子标签内原有的模型下拉/`#ragflow-chat-box`/输入区，替换为 agent 对话结构（保留"📚 知识库"子标签 iframe 不动）：
```html
<div class="agent-chat-wrap">
  <div class="agent-chat-bar">
    <label>模型</label>
    <select id="agent-model-select"></select>
  </div>
  <div id="agent-chat" class="agent-chat-box"></div>
  <div class="agent-chat-input-row">
    <textarea id="agent-input" rows="2" placeholder="输入消息，Enter 发送，Shift+Enter 换行"></textarea>
    <button id="agent-send">发送</button>
  </div>
</div>
```
注意：容器 id 与选择器（`agent-chat` / `agent-input` / `agent-send` / `agent-model-select`）须与 Step 2 的 JS 一致。原 ragflow.js 中"通用对话"相关函数不再被调用；知识库子标签逻辑保持。

- [ ] **Step 2: 实现 agent_chat.js**

创建 `static/js/agent_chat.js`：
```javascript
/* agent_chat.js — deepagents 对话：单会话内存态，SSE 消费，复用 ChatRender。 */
'use strict';
(function () {
  if (typeof marked !== 'undefined') marked.setOptions({ breaks: true });

  var messages = [];   // 内存态完整历史 [{role, content}]
  var busy = false;
  var R = null, chatEl = null, inputEl = null, sendBtn = null, modelSel = null;

  async function loadModels() {
    try {
      var r = await fetch('/api/agent/models');
      var list = await r.json();
      modelSel.innerHTML = '';
      list.forEach(function (m) {
        var o = document.createElement('option');
        o.value = m.id; o.textContent = m.name;
        if (m.default) o.selected = true;
        modelSel.appendChild(o);
      });
    } catch (e) { /* 忽略，发送时用默认 */ }
  }

  async function send() {
    var text = inputEl.value.trim();
    if (!text || busy) return;
    busy = true; sendBtn.disabled = true; inputEl.disabled = true;
    R.addUserBubble(text);
    messages.push({ role: 'user', content: text });
    inputEl.value = '';

    var ctx = R.newAiBubble();
    R.showThinking(ctx);
    var acc = '';  // 累积 assistant 文本，供多轮记忆
    try {
      var resp = await fetch('/api/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelSel.value, messages: messages })
      });
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      var reader = resp.body.getReader();
      var dec = new TextDecoder(); var buf = '';
      while (true) {
        var rd = await reader.read();
        if (rd.done) { buf += dec.decode(); break; }
        buf += dec.decode(rd.value, { stream: true });
        var idx;
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          var raw = buf.slice(0, idx); buf = buf.slice(idx + 2);
          var line = raw.replace(/^data: ?/, '');
          if (!line) continue;
          var ev = JSON.parse(line);
          if (ev.type === 'token') acc += ev.text;
          if (ev.type === 'done') { R.renderMermaidIn(ctx.bubble); }
          else { R.handleEvent(ctx, ev); }
        }
      }
    } catch (err) {
      R.appendText(ctx, '\n\n> ⚠️ ' + err.message);
    } finally {
      R.removeThinking(ctx);
      if (acc) messages.push({ role: 'assistant', content: acc });
      busy = false; sendBtn.disabled = false; inputEl.disabled = false;
      inputEl.focus();
    }
  }

  function init() {
    chatEl = document.getElementById('agent-chat');
    if (!chatEl || chatEl.dataset.inited === '1') return;
    chatEl.dataset.inited = '1';
    R = window.ChatRender.create(chatEl);
    inputEl = document.getElementById('agent-input');
    sendBtn = document.getElementById('agent-send');
    modelSel = document.getElementById('agent-model-select');
    sendBtn.onclick = send;
    inputEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });
    // 图片点击放大
    chatEl.addEventListener('click', function (e) {
      if (e.target && e.target.tagName === 'IMG' && e.target.closest('.md')) {
        window.open(e.target.src, '_blank');
      }
    });
    loadModels();
  }

  window.AgentChat = { init: init };
})();
```

- [ ] **Step 3: 触发 init（Tab 懒加载后）**

`static/tabs/ragflow.html` 是动态注入的（见 `common.js` 的 `loadAllTabPanels`）。在 ragflow.html 末尾追加一段脚本，确保注入后初始化：
```html
<script>if (window.AgentChat) window.AgentChat.init();</script>
```
（若 common.js 用 innerHTML 注入不会执行内联 script，则改为：在 `static/js/common.js` 的 tab 面板加载完成回调里、当加载的是 `tab-ragflow` 时调用 `window.AgentChat && window.AgentChat.init()`。实施时先测内联 script 是否执行：不执行就走 common.js 方案。）

- [ ] **Step 4: 编写 agent_chat.css（跟随主题变量）**

创建 `static/css/agent_chat.css`（基线样式，颜色用本项目 `common.css` 的 CSS 变量；工具卡/计划卡/气泡类名对齐 chat_render.js）：
```css
.agent-chat-wrap { display:flex; flex-direction:column; height:100%; min-height:420px; }
.agent-chat-bar { display:flex; align-items:center; gap:8px; padding:6px 10px; }
.agent-chat-bar select { background:var(--panel,#111); color:var(--text,#eee); border:1px solid var(--border,#333); border-radius:6px; padding:4px 8px; }
.agent-chat-box { flex:1; overflow-y:auto; padding:12px; display:flex; flex-direction:column; gap:10px; }
.agent-chat-input-row { display:flex; gap:8px; padding:8px 10px; border-top:1px solid var(--border,#333); }
.agent-chat-input-row textarea { flex:1; resize:vertical; background:var(--panel,#111); color:var(--text,#eee); border:1px solid var(--border,#333); border-radius:8px; padding:8px; font:inherit; }
.agent-chat-input-row button { padding:0 18px; border-radius:8px; border:none; background:var(--accent,#3b82f6); color:#fff; cursor:pointer; }
.agent-chat-input-row button:disabled { opacity:.5; cursor:not-allowed; }

/* 气泡（对齐 chat_render.js 类名） */
.agent-chat-box .row { display:flex; }
.agent-chat-box .row.user { justify-content:flex-end; }
.agent-chat-box .bub { max-width:82%; padding:8px 12px; border-radius:10px; line-height:1.6; }
.agent-chat-box .bub.user { background:var(--accent,#3b82f6); color:#fff; }
.agent-chat-box .bub.ai { background:var(--panel-2,#1b1b1f); color:var(--text,#eee); }
.agent-chat-box .bub.info { background:transparent; color:var(--muted,#9aa); font-size:13px; }
.agent-chat-box .md :is(pre,code) { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
.agent-chat-box .md pre { background:#0d1117; padding:10px; border-radius:8px; overflow:auto; }
.agent-chat-box .mermaid-svg { background:#0d1117; padding:10px; border-radius:8px; overflow:auto; }

/* 思考中 */
.thinking { display:flex; align-items:center; gap:6px; color:var(--muted,#9aa); font-size:13px; }
.thinking .dot { width:6px; height:6px; border-radius:50%; background:currentColor; animation:mmblink 1s infinite; }
.thinking .dot:nth-child(2){ animation-delay:.2s } .thinking .dot:nth-child(3){ animation-delay:.4s }
@keyframes mmblink { 0%,100%{opacity:.3} 50%{opacity:1} }

/* 工具卡片 / 计划卡片 */
.tool { border:1px solid var(--border,#333); border-radius:8px; margin:6px 0; overflow:hidden; }
.tool .hd { padding:6px 10px; cursor:pointer; display:flex; align-items:center; gap:6px; background:var(--panel-2,#1b1b1f); font-size:13px; }
.tool .hd .cap { margin-left:auto; color:var(--muted,#9aa); }
.tool .hd .cap.ok { color:#22c55e; } .tool .hd .cap.err { color:#ef4444; }
.tool .bd { padding:8px 10px; }
.tool .bd .lbl { font-size:12px; color:var(--muted,#9aa); margin:4px 0; }
.tool .bd pre { background:#0d1117; padding:8px; border-radius:6px; overflow:auto; font-size:12px; white-space:pre-wrap; }
.tool.plan { border-color:var(--accent,#3b82f6); }
.todos .todo { display:flex; gap:6px; padding:2px 0; font-size:13px; }
.todo-completed { opacity:.7; } .todo-in_progress { color:var(--accent,#3b82f6); }
```
说明：这是**功能基线**；实施后对照 mirror-cortex `main.css` 中 `.tool/.plan/.bub/.thinking` 相关规则微调视觉，颜色一律用 `var(--...)` 跟随四主题。

- [ ] **Step 5: index.html 引入 agent_chat 资源**

修改 `static/index.html`：
1. `<head>` css 区加 `<link rel="stylesheet" href="/static/css/agent_chat.css">`。
2. body 脚本区、`chat_render.js` **之后**加 `<script src="/static/js/agent_chat.js"></script>`。

- [ ] **Step 6: 前端人工端到端验证**

启动 `python run.py`，浏览器打开首页 → RAGflow Tab → 通用对话子标签：
- 模型下拉出现且默认 `DeepSeek (Agent 对话)`。
- 发"你好"，看到 token 流式渲染为 markdown 气泡。
- 发"用 mermaid 画一个包含 A→B→C 的流程图"，done 后 mermaid 渲染为 SVG。
- 发"读取 data 目录下任一 csv，用 data-plot skill 画折线图"，能看到工具卡片（read_file / bash 执行脚本）展开、计划卡片（若触发 write_todos），最终 `![](/workspace/xxx.png)` 图片内联显示。
- 切换四套主题，对话区配色跟随变化。
- 知识库子标签 iframe 仍正常。

记录异常并修复。

- [ ] **Step 7: 提交**

```bash
git add static/js/agent_chat.js static/css/agent_chat.css static/tabs/ragflow.html static/index.html
git commit -m "[新增] agent 对话前端：就地替换通用对话子标签，接入模型选择与工具/mermaid 渲染"
```

---

## Task B10: 端到端回归 + 收尾

**Files:**
- 无新增（回归验证 + 可能的小修）

- [ ] **Step 1: 单元测试全绿**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（config / sse / prompt 三组）。

- [ ] **Step 2: 全链路 skill 跑通验证**

准备一个小 CSV（若无，用 `data/` 下已有试验 txt 亦可，让 agent 自行处理路径）。在对话里让 agent 用 `data-plot` skill 出图，确认：
- 工具卡片显示脚本执行、`OK saved workspace/xxx.png`；
- `/workspace/xxx.png` 能通过静态挂载访问（`curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8501/workspace/xxx.png` 返回 200）；
- 图片在气泡内联显示。

- [ ] **Step 3: 并发生成锁验证**

连续快速发两条消息（第一条生成中即发第二条），第二条应立即出现 `⚠️ 正在生成中，请稍候` 提示气泡，不并发跑。

- [ ] **Step 4: 确认阶段 A 功能未受影响**

浏览器逐 Tab 回归：试验分析 / 仿真分析 / 配置页均与阶段 A 完成时一致；RAGflow 知识库 iframe 正常。

- [ ] **Step 5: 更新 CLAUDE.md 架构说明（可选但推荐）**

在项目 `CLAUDE.md` 的架构概要中，补充 `app/agent_runtime/`、`/api/agent/*`、`skills/`、`workspace/` 的说明（一句话即可，反映新结构）。

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "[优化] agent 对话移植端到端回归通过，更新架构说明"
```

---

## Self-Review（作者自检，已完成）

- **Spec 覆盖**：设计 §3（agent_runtime 四模块 + 路由 + 去 Flask 适配 + 依赖 + workspace 挂载）→ B0–B7；§4（chat_render 移植 + agent_chat.js + ragflow.html + vendor + mermaid + 主题）→ B8–B9；§5 skills 机制 + 示例 → B3/B6；§6 SSE 协议 → B2；§7 错误处理（生成锁/error 气泡/mermaid 降级）→ B5/B7/B8/B10；§8 风险 R1（依赖）→ B0，R2（Linux shell）→ prompt 按 platform 分支 + B10，R3（路径两分）→ B6/B10。全覆盖。
- **无占位符**：每步含实际代码/命令；移植文件（sse.py 全文、chat_render 新增块、agent_chat.js 全文、prompt.py 全文）均给出可直接落地内容；agent.py 第 27-160 行逐字复制点明确指向源文件行号。
- **类型/名称一致**：`get_agent_model` 返回 dict 键（model/base_url/api_key/context_window）在 B1 定义、B4/B7 一致消费；`get_lock`/`get_agent(model_id, model_cfg)` 在 B5 定义、B7 一致调用；`StreamTranslator(skip_count=)`/`_sse` 在 B2 定义、B7 使用；前端 `window.ChatRender.create` 返回含 `renderMermaidIn`（B8 新增）在 B9 调用；DOM id `agent-chat/agent-input/agent-send/agent-model-select` 在 B9 Step1 与 Step2 一致。
- **已知实施注意点**：B9 Step3 的 Tab 懒加载内联 script 是否执行需实测，已给出 common.js 回退方案；B0 依赖冲突为最高风险，作为首任务先行验证。
