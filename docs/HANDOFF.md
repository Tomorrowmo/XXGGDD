# 交接文档 —— 组合动力智能评估平台重构（v2）

> 新会话直接读这份即可接手。最后更新：2026-07-14

## 项目一句话
把「航天发动机热试车/仿真数据评估」老项目重构为 **DeepAgents 架构的多源评估平台**：多单位仿真/实验数据入库→按工况对齐→多源对比评分→评估报告→AI 对话。工作目录 `d:\Git\XGDRSight\HYY_PerfomanceAnalysis`。

## 怎么跑起来
```bash
# 基础环境：D:\TOOL\Conda\conda（已装 sqlalchemy/langchain/deepagents/langchain-openai/simparse 依赖）
cd d:\Git\XGDRSight\HYY_PerfomanceAnalysis
python -m uvicorn app.main:app --host 0.0.0.0 --port 8501 --log-level warning   # 后台跑
# 前端： http://localhost:8501/platform     API文档： /docs
python -m pytest tests/ -q      # 71 用例全过
export PYTHONIOENCODING=utf-8    # Windows 终端中文防乱码
```
前端源文件是 `docs/prototype.html`；`/platform` 实际服务的是打包版 `docs/组合动力智能评估-原型.html`。**改完 prototype.html 要重新打包**：
```bash
{ echo '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>组合动力智能评估 · 原型</title></head><body>'; cat docs/prototype.html; echo '</body></html>'; } > "docs/组合动力智能评估-原型.html"
```

## 关键环境/资产路径（都可用，已验证）
- **切片渲染（2026-07-15 已独立）**：渲染代码 vendored 进平台 `app/services/render/`（`simagent_render.py` + `openfoam_loader.py`，纯标准 VTK），**不再依赖 SimGraph2 仓库**。OpenFOAM 算例用平台基础环境（VTK 9.6+）即可出图（`viz._render_python` 默认 `sys.executable`），完全自洽。仍走 `render_runner.py` **子进程**隔离出五图（slice_X/Y/Z + surf_a/b）。仅 **Fluent .cas.h5 等需 Romtek** 的格式才回退 `D:\TOOL\Conda\conda\envs\PostProcessTool\python.exe`（VTK9.4.1+Romtek）+ SimGraph2/PostEngine。结果含 `engine` 字段（`vendored-vtk` / `simgraph2-romtek`）。测试 `tests/test_render_vendored.py`。
- **simparse 解析**：`D:/Git/GitBubProj/simcli/sim-parse/src`（`app/services/simparse_adapter.py` 直调，tier_3_metadata/tier_5_qoi 等）
- **sim-knowledge 判据**：`D:/Git/GitBubProj/simcli/sim-knowledge`（12 域 criteria.yaml）
- **SimGraph2**（复用来源）：`D:/Git/SimGraph2`（切片渲染 `simagent_render.render_case`；不是 DeepAgents）
- **测试算例**：`D:/Git/SimGraph2/test_data/DLR_A_LTS`（openfoam 燃烧，真解析+切片）；`data/试车A01.txt`（真实验，已造）

## 架构（app/ 下）
- `settings.py` 去写死配置中心 + LLMConfig（对齐 DataAgent：LLM_PROVIDER/DEEPSEEK_API_KEY/BASE_URL/MODEL）
- `db/{database,models}.py` SQLAlchemy 评估元数据：Unit→Delivery→Case→(Measurement→OperatingPoint)+Evaluation+Conversation/Message+四级置信度(HIGH/MED/LOW/PENDING)
- `services/`：experiment(可配置解析+阶段分割+稳态取真值)、criteria(判据+评级)、compare(多源评分)、operating_point(工况对齐auto/rule/manual+PENDING兜底)、ingest(去重+解析+对齐+写库)、evaluation(装配对比+报告)、seed(XF-2演示)、simparse_adapter、viz(切片)、llm(LLMClient BYOK)、search(NL检索)
- `agents/`：deep_agent(DeepAgents主编排，`create_deep_agent(system_prompt=...)`)、prompts(渊CFD/析试验子agent)、tools(带harness路径守卫)、model(ChatOpenAI from llm config)、harness(安全拦截)
- `routers/` v2 API：library/compare/report/search/knowledge/agent/chat_v2/llm_config/analysis（都挂在 `/api/v2/*`）+ 保留旧路由

## 真实性现状（用户要"全改真"）
✅ **已真**：数据资源库(卡片/树/统计/预览抽屉/入库弹窗/NL检索)、对比评估(排名+逐项偏差表+空状态)、评估报告、仿真分析·单算例、试验分析·单车次、通用对话(持久化会话+流式，`/api/v2/chat/conversations`)、大模型配置(BYOK+测试)。前端无数据一律显示空状态，不再回退 mock。
⚠️ **还是 mock（下一步接真）**：
1. ~~仿真分析·**多算例对比** / 试验分析·**多车次对比**~~ ✅ **已接真**（2026-07-14）：
   - 后端 `GET /api/v2/cases/sim-compare?ids=` / `exp-compare?ids=`（`app/routers/analysis.py`），统一以库内 `Measurement` 为源（种子/真实入库一致）。sim=网格最细者为基准算逐 QOI 偏差 + 网格无关性判定（HIGH/MED/LOW）；exp=逐关键量 均值±σ/CV/离群车次（>2 票判离群）+ 剔离群后 CV。测试 `tests/test_multi_compare.py`（5 例）。
   - 前端 `liveSimMulti`/`liveExpMulti`（多选 checkbox `.mchip` + 对比按钮，无数据/不足 2 个/无共同量→诚实空状态）。**注意路由顺序**：`analysis_router` 必须在 `library_router` 之前 include，否则 `/cases/sim-compare` 被 `/cases/{case_id:int}` 拦成 422。
2. ~~**PENDING 人工对齐面板**~~ ✅ **已接真**（2026-07-14）：前端 `livePending`（`#pending-panel` 挂在资源库工具栏下），列出 `/api/v2/pending` 各待对齐项，每项一个输入框（datalist 提示已有工况）+ 指定按钮 → POST `/links/{id}/assign-op` → 刷新 pending/cases/units/compare/report/exp-multi + 收起侧栏红点。无 PENDING 时面板隐藏。HTTP 流程测试 `tests/test_pending_api.py`（2 例）。
3. ~~**报告历史列表**~~ ✅ **已接真**（2026-07-14）：`liveReport` 现同时渲染左侧 `.report-list` 与正文——历史列表 = 各"能出报告的工况"（有实验真值 + 仿真源，逐个探测 `/report/{op}` 的 ok），点击即加载该工况报告正文；无则显空状态。报告未落库为独立实体（`build_report` 按需算），列表即"可评估工况"。`导出 PDF`/`新建`/`追加知识库` 按钮仍是 toast（真 Markdown 导出端点 `/report/{op}/export` 已就绪未接按钮）。API 测试 `tests/test_report_api.py`（3 例）。
4. ~~**配置·解析/判据配置**~~ ✅ **已接真**（2026-07-14）：后端 `app/services/config_store.py` + `app/routers/config.py`：`GET /api/v2/config/parse` 读真实 `settings.experiment/physics` + 汇报判据来源（sim-knowledge 真扫出 12 域）；`PUT` 改写白名单字段（分隔符/编码/headerIndex/时间列/通道正则/大气修正/γ/R）并落 `parse_config.json`（gitignore），启动 `config_store.load_overrides()` 应用回。正则非法→400。前端 `liveConfig` 表单编辑 + 保存并落盘；判据段只读列 12 域。测试 `tests/test_config_api.py`（3 例）。**注意**：`settings` 是模块级单例，PUT 改的是内存值，测试用例改后要还原避免污染其它用例。
5. ~~**知识库检索**~~ ✅ **已接真（诚实三态）**（2026-07-14）：`app/routers/knowledge.py` 重写：`GET /knowledge/status` + `POST /knowledge/query[/stream]` 三态——RAGflow 已配（env `RAGFLOW_API_URL`+`RAGFLOW_API_KEY`，本地未配）→ 检索占位；否则大模型已配 → **LLM 直答兜底，明确标注无检索、sources 恒为 []、不伪造出处**；都无 → 提示未配置。前端 `liveKB` 覆盖 mock：按 status 显模式徽章（RAGflow检索 / LLM兜底·无出处 / 未配置）+ 诚实开场 + 改占位/底部提示，流式解析 meta.note+delta。测试 `tests/test_knowledge_api.py`（5 例）。真检索仍需部署 RAGflow（TODO 在 query 里）。
6. 对比 L2/L1 视图（已隐藏，只留 L3 真数据；L1 单位评级≈L3排名）

**至此 ①–⑤ 全部接真**（89 pytest 全过）。前端所有主功能无 mock 回退，无数据一律诚实空状态。

前端"实时接线"逻辑都在 `docs/prototype.html` 末尾一个 IIFE 里：`liveCompare/liveCases/liveUnits/liveReport/liveNL/liveLLM/liveChat/liveExp/liveSim`，无后端时优雅回退 mock（探测 `/api/v2/cases` 是否可达）。主脚本的全局函数（openDrawer/refreshSel/go/toast/nlQuery）被 live 脚本覆盖或复用。

## Git / 安全
- 远程：`origin`=coding.net(romtek)；`github`=https://github.com/Tomorrowmo/XXGGDD.git（已推 master，2 commit）
- **`llm_config.json` 含用户真实 DeepSeek key**（`sk-fd13...`）——已 gitignore，**绝不提交**。`.gitignore` 已加 `.env / llm_config.json / *.db / var/ / ingest/`
- `models.json`/`rag.json` 已脱敏（当前状态）；git 历史里旧版含占位假 key + 内网 RAGflow token（低危，未清历史）
- 推送前务必扫 `git diff --cached | grep sk-fd133`

## 唯一没验证的
LLM/agent **真实对话回复**：agent 已构建成功(CompiledStateGraph)，LLMClient/流式都通，但需有效 `DEEPSEEK_API_KEY`。用户已在配置页填了真 key（存 llm_config.json，未提交）。测试连接返回 401=用了输入的key（网络通）。

## 设计文档
`docs/00-需求与定位.md` … `04-目标架构与技术选型.md`（含验证状态）。前端原型 artifact：https://claude.ai/code/artifact/61838a3d-7ebe-47a3-aca6-912582f10b68

## 下一步建议
接着把 ⚠️ 那 6 块 mock 改真：优先 ①多算例/多车次对比（复用 analysis 端点+多选）②PENDING面板（端点已就绪）③配置·解析配置。知识库检索诚实标注需 RAGflow。每改一块配测试、重新打包 standalone、推 github。
