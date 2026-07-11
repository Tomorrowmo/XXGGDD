# CLAUDE.md

航天发动机热试车数据智能分析系统 — Claude Code 项目指南。

## 项目概述

基于大模型 Agent 的火箭发动机热试车数据自动分析 Web 应用。FastAPI 后端 + 原生 HTML/CSS/JS 前端，部署于 8×H100 GPU 服务器。

## 常用命令

```bash
# 激活环境
source /opt/miniconda3/etc/profile.d/conda.sh && conda activate gy_pytorch

# 启动服务（主入口）
python demo_server.py
# 服务运行在 http://0.0.0.0:8501，API 文档 http://localhost:8501/docs

# 启动早期 Streamlit 原型（保留参考）
streamlit run app.py --server.port 8501

# 依赖安装
pip install -r requirements.txt
```

## 架构概要

```
demo_server.py (FastAPI, 主入口)
  ├── 挂载 static/、results_png/、Case/、output_plots/ 为静态文件
  ├── 挂载 fluent_router（/api/fluent/*）
  ├── 试验数据文件管理 API（/api/upload、/api/files 等）
  ├── 数据查询 / 统计 API（/api/data/info、/api/stats/compute 等）
  ├── 交互图表 API（/api/chart/pressure-curve、/api/chart/channels）
  ├── LLM 诊断 API（/api/llm/diagnose，SSE 流式）
  ├── VLM 分析 API（/api/vlm/*、/api/fluent/vlm/analyze，SSE 流式）
  ├── RAGflow 通用对话 API（/api/ragflow/*，SSE 流式）
  ├── 模型配置管理 API（/api/models/*）
  └── RAG 知识库配置 API（/api/rag/*）

src/
  ├── plotter.py          — 数据读取、流道提取、通道统计、Plotly 图表
  ├── llm_client.py       — DeepSeek API 流式调用 + 自动校验规则 + 诊断 prompt
  ├── vlm_client.py       — VLM 图像/CFD 云图分析 + 多轮对话（OpenAI 兼容）
  ├── rag_client.py       — 通用模型路由（从 models.json 读取配置）
  └── QJZ_fluent_post/    — Fluent HDF5 后处理
      ├── http_api.py         — APIRouter，/api/fluent/* 路由
      ├── zones.py            — .cas.h5 zone 解析
      ├── face_geometry.py    — 面法向量 / 面积
      ├── wall_forces.py      — 壁面力积分 + JSON/文本报告
      ├── inlet_conditions.py — 入口参数提取
      ├── symmetry_plot.py    — 对称面 PyVista 云图
      ├── x_slice_average.py  — 沿程面平均 + Matplotlib 曲线
      └── local_case_upload.py — 算例上传后台任务
```

## 关键约定

### 数据格式

- 试验数据 TXT 文件：逗号分隔，UTF-8 编码，headerIndex=10（第 11 行是列名）
- 时间列始终是第 0 列（`Time (s)`）
- 所有压力值使用前需 +0.101325 MPa 大气压修正（见 `src/plotter.py` 和 `src/llm_client.py`）
- 流道通道通过 header 中的"流道+数字"正则匹配提取（`src/plotter.py:extract_channels`）

### LLM 诊断校验规则

- 压力最小值 < 0 → 严重异常（已修正大气压后不应出现负值）
- 压力最大值 > 10 MPa → 超出常规工作范围
- 标准差 > 均值×2 且均值 > 0.01 → 波动异常剧烈
- 正常范围：0.00001 – 10 MPa

### API Key 管理

- 直接 API Key 写在 `models.json` 各模型配置的 `api_key` 字段（保存时脱敏为 `****`，前端传入 `****` 时保留原值）
- 环境变量方式：在 `models.json` 设置 `api_key_env` 字段指定环境变量名
- `llm_client.py` 使用 `DEEPSEEK_API_KEY` 环境变量，不走 models.json

### GPU 分配

- 本项目固定使用 cuda:6 和 cuda:7（GPU #7 和 #8），不要使用其他 GPU

### 模型配置

- `models.json` 包含 `id`、`name`、`provider`、`api_base`、`model_name`、`multimodal` 等字段
- `provider: "local"` 的模型会自动排在选择器前列
- `multimodal: true` 的模型用于 VLM 分析任务

### 前端

- `static/index.html` 是主页面（4 Tab：RAGflow / 仿真分析 / 试验分析 / 敬请期待 + 1 配置页）
- `static/index_qjz.html` 是备用入口（无模型配置 Tab）
- `static/docs.html` 是使用文档页面
- 4 套主题：deepspace（默认）/ minimal / cockpit / sunset，通过 `data-theme` 属性切换
- 所有 SSE 流式接口要求 Nginx 不缓冲（`X-Accel-Buffering: no`）

### 目录

- `data/` — 用户上传的试验数据
- `Case/` — Fluent 算例（`Case/<算例名>/*.cas.h5, *.dat.h5`）
- `results_png/` — 预生成分析结果图片
- `output_plots/` — Fluent 后处理输出（由 API 动态生成）

## 不在此仓库的内容

- Streamlit 原型 `app.py` 已不再维护，仅保留参考
- 原始资源文件目录 `resourceData/` 已不在此仓库中
