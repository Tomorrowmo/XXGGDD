# 设计文档：代码重构 + deepagents 对话移植

- 日期：2026-07-11
- 项目：航天发动机热试车数据智能分析系统（HYY_PerfomanceAnalysis）
- 状态：待审阅

## 1. 背景与目标

本次工作包含两个**相互独立**的子项目，按顺序实施（先 A 后 B，B 落在 A 的新结构上）：

- **阶段 A（重构）**：把 `demo_server.py` 启动的整套代码 + `src/` 收拢进 `app/` 包，纯搬迁 + 拆分 + 改 import，**功能零变化**。
- **阶段 B（移植）**：把 `D:\proj\vc\mirror-cortex` 的 deepagents 对话能力（对话界面 + agent 逻辑 + skills 逻辑 + 工具调用可视化 + 图片链接 + mermaid + markdown）移植过来，改造为本项目的 FastAPI 接口与界面，**就地替换**现有 RAGflow"通用对话"子标签。agent 用 DeepSeek（复用 mirror-cortex 的 API）。

### 关键决策（已与用户确认）

| 决策点 | 结论 |
| --- | --- |
| 阶段拆分 | 先重构（A）→ 后移植（B），各自可独立验证 |
| 移植深度 | 轻量对话内核：**去掉** 登录/用户系统/数据库/作业管理/Celery/3D 预览/OIDC |
| skills | 只搬**机制**（扫描 SKILL.md → 注入提示 → agent 按需执行脚本）+ 最小示例 skill；不搬依赖重型求解环境的具体 skill |
| 对话历史 | 单会话内存态，前端传完整 messages，后端不落库 |
| 工作区 | 固定 `workspace/` 目录，agent 文件产物写此处 |
| DeepSeek 配置 | 并入 `models.json` 统一管理，agent 模型可选、DeepSeek 默认选中 |
| 前端集成 | 就地替换 RAGflow"通用对话"子标签；保留"知识库 iframe" |
| 第三方库 | 全部下载到 `static/vendor/` 本地引入，不依赖外网 CDN |
| routers 拆分 | 拆分（阶段 A 的主要价值） |
| Fluent 包名 | 改小写 `qjz_fluent_post` |

## 2. 阶段 A：重构为 `app/` 包

### 2.1 目标结构

```
app/
├── __init__.py
├── main.py                 ← 原 demo_server.py：FastAPI 实例、静态挂载、include routers、__main__ 启动
├── config.py               ← 集中路径常量（ROOT、DATA_DIR、CASE_DIR、OUTPUT_PLOTS_DIR、WORKSPACE_DIR…）
├── routers/                ← 按功能拆分的路由
│   ├── __init__.py
│   ├── files.py            (上传/删除/重命名/data info)
│   ├── charts.py           (chart/pressure-curve、chart/channels)
│   ├── diagnose.py         (llm/diagnose、stats/compute)
│   ├── vlm.py              (vlm/*)
│   ├── ragflow.py          (ragflow/* —— 现有转发式对话 + 知识库；阶段 B 在此新增 agent 路由或独立 agent_chat.py)
│   └── models_config.py    (models/*、rag/*)
└── core/                   ← 原 src/ 的模块
    ├── __init__.py
    ├── plotter.py
    ├── llm_client.py
    ├── vlm_client.py
    ├── rag_client.py
    └── qjz_fluent_post/    ← 原 src/QJZ_fluent_post/（改小写），含 http_api.py 的 create_fluent_router
        ├── __init__.py
        ├── http_api.py
        ├── output_cache.py
        ├── symmetry_plot.py
        ├── x_slice_average.py
        ├── wall_forces.py
        ├── inlet_conditions.py
        ├── face_geometry.py
        ├── local_case_upload.py
        └── zones.py

根目录保留：static/  data/  Case/  output_plots/  results_png/  models.json  rag.json  requirements.txt
根目录新增：run.py（薄启动脚本：uvicorn app.main:app）
根目录保留 shim：demo_server.py（3 行，转发到 app.main，兼容旧引用）
```

### 2.2 拆分规则

- `main.py` 只保留：FastAPI app 装配、静态目录挂载、`include_router`、`create_fluent_router` 接入、`if __name__ == "__main__"` 启动块。
- 原 614 行 `demo_server.py` 里按功能分组的路由处理函数，逐组搬到 `routers/*.py`，每个文件用 `APIRouter()`。
- `src/` 各模块整体搬到 `app/core/`；`import src.xxx` → `import app.core.xxx`；`from src.QJZ_fluent_post...` → `from app.core.qjz_fluent_post...`。
- 静态资源 `static/` 与数据目录（`data/`、`Case/`、`output_plots/`、`results_png/`）**不移动**，仅在 `main.py` 挂载路径不变。

### 2.3 验收标准（阶段 A）

`python run.py` 启动后（等价旧 `python demo_server.py`），4 个 Tab 全部功能与重构前**行为一致**：
- 试验分析：上传/统计/压力曲线/LLM 诊断/VLM 对话
- 仿真分析：Fluent 后处理各接口
- RAGflow：原转发式通用对话 + 知识库 iframe
- 配置：models.json / rag.json 读写

**行为零变化是唯一验收标准。** 不新增功能、不改接口签名、不改前端行为。

## 3. 阶段 B（后端）：deepagents 对话内核接入 FastAPI

### 3.1 新增 `app/agent_runtime/` 包

从 mirror-cortex 移植并去 Flask 化：

```
app/agent_runtime/
├── __init__.py
├── agent.py       ← 移植 mirror-cortex app/agent_runtime/agent.py
│                     RobustLocalShellBackend + StripImageBlocksMiddleware + build_agent()
│                     去掉 flask current_app，改为显式传 config
├── sse.py         ← 原样移植 StreamTranslator（token/tool_call/tool_result 翻译），纯逻辑
├── prompt.py      ← 移植 agent_prompt.py 的 skills 清单扫描 + 系统提示词（裁剪用户/作业相关内容）
└── config.py      ← agent 模型配置读取（见 3.4）
```

### 3.2 新增路由（对话核心）

在 `app/routers/agent_chat.py`（或并入 `ragflow.py`）：

- `POST /api/agent/chat` → `StreamingResponse(media_type="text/event-stream")`，响应头 `X-Accel-Buffering: no`
  - 请求体：`{ "model_id": "<models.json 里的 id>", "messages": [ {role, content}, ... ] }`
  - 流程：读取选中模型配置 → `build_agent(model_cfg)` → `agent.stream(inputs, stream_mode=["values","messages"])` → 用 `StreamTranslator(skip_count=len(输入messages))` 把事件翻成 SSE 逐条 yield → 末尾 `data: {"type":"done"}`
  - 把 mirror-cortex Flask `Response(gen, mimetype=...)` 换成 FastAPI `StreamingResponse`，生成器内部逻辑（agent.stream 消费 + translator）照搬。

### 3.3 去 Flask 化适配点

1. `current_app.config["BASE_DIR"] / ["SKILLS_DIR"]` → 从 `app/config.py` 取：`BASE_DIR = 项目根`、`SKILLS_DIR = ROOT/skills`。
2. **backend 根 = 项目根**（deepagents SkillsMiddleware 需 `read_file` 读 `skills/` 全文，skills 必须落在 backend 根内）；agent 文件产物写 `workspace/`，通过系统提示词告知 agent"产物写到 `/workspace/`"。沿用 mirror-cortex 的虚拟路径机制。
3. `settings_service.get_llm()` → 换成 `agent_runtime/config.py` 从 `models.json` 读选中模型 + DeepSeek 默认。
4. **Agent 实例管理**：单用户，简化为**进程级单例缓存 + 一把生成锁**（防并发同跑一个 agent）；mirror-cortex 的按用户缓存机制不需要。

### 3.4 模型配置（并入 models.json）

- 在 `models.json` 新增一条 DeepSeek 条目（默认选中），字段：`id`、`name`、`api_base=https://api.deepseek.com`、`model_name=deepseek-v4-flash`、`api_key`（复用 `.mirror.env` 的 `sk-17d3...`，或走 `api_key_env`/环境变量）、`context_window=1M`（或复用现有 `max_tokens` 语义，另加窗口字段）。
- `build_agent(model_cfg)` 用 `ChatOpenAI(model, base_url, api_key, temperature=0, profile={"max_input_tokens": context_window})` 构造，`context_window` 支持 `1M/256K/数字` 解析。
- **约束**：deepagents 依赖模型支持 function/tool calling。DeepSeek 支持；本地 vLLM 模型不一定。前端下拉默认列出全部、DeepSeek 置顶默认选中；可后续加 `agent_capable: true` 字段过滤不支持工具调用的模型。

### 3.5 依赖新增（装入 conda `gy_pytorch`）

```
deepagents==0.6.9
langgraph==1.2.5
langchain==1.3.9
langchain-core==1.4.7
langchain-openai==1.3.1
```

严格锁版本对齐 mirror-cortex，避免 deepagents 与 langchain 接口漂移。`langchain-anthropic`/`google-genai` 不需要，DeepSeek 走 `langchain-openai`。

### 3.6 workspace 静态挂载

`app.mount("/workspace", StaticFiles(directory=WORKSPACE_DIR))`，使 agent 生成的图片可经 `/workspace/xxx.png` 被前端 markdown 图片语法加载。

## 4. 阶段 B（前端）：就地替换"通用对话"子标签

### 4.1 移植/新增文件

```
static/js/chat_render.js   ← 原样移植（window.ChatRender IIFE）：气泡/工具卡/计划卡/markdown/代码高亮/图片内联
static/js/agent_chat.js    ← 新写，替代 ragflow.js 的对话逻辑：
                              发消息 → fetch POST /api/agent/chat → 读 SSE 流 → R.handleEvent(ctx, ev) → 末尾 done
static/css/agent_chat.css  ← 移植 main.css 对话/工具卡/计划卡样式，改写为本项目 4 主题 CSS 变量
static/vendor/             ← 本地第三方库：dompurify、highlight.js（+css）、mermaid
```

### 4.2 改动 `static/tabs/ragflow.html`

- "💬 通用对话"子标签：原简单 `#ragflow-chat-box` + 单模型下拉 → 换成 agent 对话界面（模型选择器 + 消息流容器 + 输入框 + 发送 + "思考中…"指示）。
- "📚 知识库"子标签：保持不动（iframe）。
- 模型选择器：选项 = `models.json` 里适合 agent 的模型 + DeepSeek（默认选中）。

### 4.3 新增第三方库（本地 vendor）

| 库 | 用途 | 现状 |
| --- | --- | --- |
| DOMPurify | markdown 渲染防 XSS | 本项目缺，移植依赖 |
| highlight.js | 代码块高亮 | 本项目缺，移植依赖 |
| mermaid | **★新增能力**：mermaid 图渲染（mirror-cortex 也没有） | 全新 |
| marked | markdown 解析 | 本项目已有 |

### 4.4 mermaid 渲染（唯一新写的渲染能力）

在 `chat_render.js` 的 `appendText()` markdown 渲染之后追加一步：扫描结果中的 ` ```mermaid ` 代码块 → `mermaid.render()` 替换为 SVG。因流式逐字更新：
- 仅在代码块**闭合完整**时渲染（避免半截语法报错）；
- 加防重复渲染标记；
- 语法错误时捕获、降级为原始代码块显示，不打断整条消息。

### 4.5 图片生成链接

无需额外前端工作：agent 输出 `![](/workspace/result.png)`，`marked` + `/workspace` 静态挂载即内联显示。工具卡片返回的图片路径作为文本展示。

### 4.6 主题适配

移植的 `main.css` 配色改写为本项目 `common.css` 的 CSS 变量（`var(--...)`），使对话界面跟随 deepspace/minimal/cockpit/sunset 四主题切换。

## 5. skills 机制

- 目录 `skills/`（项目根），结构：`skills/<name>/SKILL.md` + `scripts/` 等。
- 加载：deepagents 的 `create_deep_agent(..., skills=["/skills"])` 的 SkillsMiddleware 自动扫描 `SKILL.md` 的 YAML frontmatter（`name` + `description`），注入系统提示的技能清单；`prompt.py` 移植扫描逻辑。
- skills 目录**只读**：`RobustLocalShellBackend._ensure_not_skills` 拦截对 skills 的写/编辑。
- **最小示例 skill**：新建 1 个能在本项目环境（conda `gy_pytorch`，Linux）跑通的示例（如数据读取+画图），验证"agent 读 SKILL.md → 执行脚本 → 产物图片内联"全链路。不搬 aircraft-modeling/piflow/fluent/abaqus 等依赖重型求解环境的 skill。

## 6. SSE 事件协议（移植自 mirror-cortex，不变）

```
data: {"type": "token", "text": "文本片段"}
data: {"type": "tool_call", "id": "...", "name": "...", "args": {...}}
data: {"type": "tool_result", "id": "...", "output": "...", "ok": true|false}
data: {"type": "error", "message": "..."}
data: {"type": "done"}
```

- 工具输出 SSE 推送截断 2000 字符（`OUTPUT_LIMIT`），防前端卡顿。
- `WriteTodos` 工具 → 前端渲染为"计划卡片"（TODO 列表 + ✅/🔄/⬜）。
- 前端 `chat_render.js` 的 `handleEvent(ctx, ev)` 消费上述事件。

## 7. 错误处理

- SSE 中途异常 → 后端发 `{"type":"error"}`，前端渲染 ⚠️ 提示气泡。
- agent 生成锁：并发请求时第二个返回"上一轮进行中"，不并发跑同一 agent。
- 选到不支持工具调用的模型 → 报错透传到前端 error 气泡。
- mermaid 语法错误 → 捕获降级为原始代码块，不打断消息。

## 8. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| **R1 依赖冲突**：deepagents+langgraph+langchain 装入 `gy_pytorch` 可能与现有包冲突 | 阶段 B **首个前置步骤**：试装并锁版本；冲突则记录、必要时独立 venv |
| **R2 Windows→Linux shell**：移植源码有 Windows 特判（`dir /s`、GBK 解码），本项目部署 Linux | Windows 特判在 Linux 不命中、无害；确认工作/编码路径在 Linux 正常；示例 skill 用跨平台 Python |
| **R3 路径两分**：backend 根=项目根、产物=workspace 的虚拟路径机制易出错 | 移植后用示例 skill 专门验证路径解析 |

## 9. 明确不做（YAGNI）

登录/用户系统、SQLAlchemy 数据库、多会话持久化、作业管理面板、Celery worker、3D/STL/VTK 预览、OIDC 认证、编码环境（coding 模式）。

## 10. 实施顺序与验收

1. **阶段 A 重构** → 验收：`python run.py` 启动，4 Tab 行为与重构前完全一致。
2. **阶段 B-0 依赖** → 验收：deepagents 全套装好、`import` 通过。
3. **阶段 B 后端** → 验收：`/api/agent/chat` 能流式返回 token/tool 事件。
4. **阶段 B 前端** → 验收：对话子标签能发消息、看 token 流、工具卡片、计划卡片、markdown/高亮/mermaid/图片内联、切换模型。
5. **端到端** → 验收：最小示例 skill 跑通"读 SKILL.md → 执行脚本 → 产物图片内联"。
