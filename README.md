# 航天发动机热试车数据智能分析系统

## 研究方向

航天发动机专业，聚焦液体/固体火箭发动机点火燃烧试验的数据智能分析。

## 项目目标

构建基于大模型 Agent 的发动机热试车数据自动分析系统，实现从原始试验数据到结构化分析报告的全流程自动化。

核心分析工作流：

```
数据输入 → Python 数值分析（统计/信号处理） → LLM/VLM 多模态分析 → 格式化报告输出
```

## 输入数据

| 数据类型 | 来源 | 格式 |
|---------|------|------|
| 试车遥测数据 | 点火燃烧试验传感器采集 | TXT（逗号分隔）/ CSV |
| CFD 仿真数据 | Fluent 求解器输出 | .cas.h5 / .dat.h5（HDF5） |
| 火焰图像 | 单反相机拍摄 | JPG / PNG |

---

## 技术栈

| 组件 | 方案 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| 前端 | 原生 HTML/CSS/JS（4 套主题，毛玻璃 UI） |
| 交互图表 | Plotly（Python 生成 JSON） + Plotly.js（前端渲染） |
| 数值计算 | NumPy、pandas、SciPy |
| CFD 后处理 | h5py、PyVista、Matplotlib |
| LLM 调用 | OpenAI SDK（兼容 DeepSeek / 本地 vLLM 等多模型） |
| VLM 多模态 | Qwen2.5-VL-7B（vLLM 本地部署）+ OpenAI 兼容端点 |
| RAG 知识库 | RAGflow（iframe 嵌入） |
| 环境管理 | conda（gy_pytorch） |

## 开发环境

| 项目 | 说明 |
|------|------|
| 本地开发机 | Windows 10，VS Code（Remote-SSH 连接远程服务器） |
| 远程服务器 | Ubuntu，8 × NVIDIA H100 GPU |
| GPU 分配 | 本项目使用 cuda:6 和 cuda:7，其余 GPU 归团队其他成员使用 |
| Python 环境 | conda 虚拟环境 `gy_pytorch` |

### 启动方式

```bash
source /opt/miniconda3/etc/profile.d/conda.sh && conda activate gy_pytorch
python demo_server.py
```

### 访问地址

| 地址 | 说明 |
|------|------|
| `http://10.69.140.82:8501` | 校园网主访问地址 |
| `http://localhost:8501` | 本地访问 |
| `http://localhost:8501/docs` | FastAPI 自动生成的 API 文档 |

---

## 项目结构

```
data_auto_analysis_06/
├── demo_server.py              # FastAPI 主入口 + REST API 路由定义
├── app.py                      # 早期 Streamlit 原型（保留参考）
├── A00_parameterData.py        # 传感器坐标/索引定义、数据读取函数
├── B01_blowoff_pressure.py     # 熄火压力分析脚本
├── models.json                 # 多模型配置（本地 vLLM + 云端 API）
├── rag.json                    # RAGflow 知识库 iframe URL 配置
├── requirements.txt            # Python 依赖清单
├── src/
│   ├── __init__.py
│   ├── plotter.py              # 数据读取、流道提取、统计计算、Plotly 图表生成
│   ├── llm_client.py           # DeepSeek API 流式调用 + 自动校验诊断
│   ├── vlm_client.py           # VLM 图像分析 + CFD 云图分析 + 多轮对话
│   ├── rag_client.py           # 通用模型调用模块（models.json 路由）
│   └── QJZ_fluent_post/        # Fluent CFD HDF5 后处理模块
│       ├── __init__.py
│       ├── http_api.py         # Fluent 相关 API 路由（APIRouter）
│       ├── zones.py            # 解析 .cas.h5 zone 拓扑与名称
│       ├── face_geometry.py    # 面法向量、面积、中心计算
│       ├── wall_forces.py      # Wall 边界压力与黏性力面积分
│       ├── inlet_conditions.py # 入口边界邻接单元平均量 + 质量流量
│       ├── symmetry_plot.py    # Symmetry 边界拼接网格 + 标量场截图
│       ├── x_slice_average.py  # 沿 x 方向薄层单元面平均 + 曲线图
│       └── local_case_upload.py # 算例文件上传校验与本地写入
├── static/
│   ├── index.html              # 主前端页面（4 Tab + 4 主题）
│   ├── index_qjz.html          # 替代入口页面
│   └── docs.html               # 使用文档页面
├── data/                       # 用户上传的试验数据文件目录
├── Case/                       # Fluent 算例目录（.cas.h5 / .dat.h5）
├── results_png/                # 分析结果图片
├── output_plots/               # Fluent 后处理生成的可视化输出
└── QJZ_20260514_demo/          # 演示数据目录
```

---

## 功能模块

### 1. RAGflow 通用对话 & 知识库

- **通用对话**：选择任意已配置模型，SSE 流式多轮对话，Markdown 渲染
- **知识库**：iframe 嵌入 RAGflow 共享知识库页面
- **模型测试**：一键测试模型 API 连接可达性

### 2. 仿真分析 — Fluent HDF5 后处理

- **算例管理**：扫描 `Case/` 目录下的子目录，自动配对 .cas.h5 / .dat.h5
- **算例上传**：Web 端上传 Fluent 文件至 `Case/<算例名>/`，含 SSE 进度推送
- **边界列表**：解析 zone 拓扑（名称、类型、面数）
- **入口参数**：自动识别 inlet 边界，计算速度、静压、静温、质量流量
- **壁面力**：对所有 wall 边界积分压力与黏性力，输出三分量力
- **对称面云图**：拼接所有 symmetry 面，生成 Pressure/Temperature/Mach 三张 PNG
- **沿程面平均**：沿 x 方向薄层平均（P_static、T_static、Mach、T0、P0、HRR），生成 CSV + 可调范围曲线图
- **VLM 云图分析**：选择云图 + 多模态模型，AI 解读 CFD 仿真结果

### 3. 试验分析

- **数据管理**：上传 TXT/CSV 文件（点击/拖拽/进度条），文件列表增删改重命名
- **数据加载**：解析 header（headerIndex=10），显示统计卡片 + 列名速查表（支持搜索）
- **交互式压力曲线**：Plotly 渲染，多通道选择，颜色区分，悬停显示数值，框选缩放
- **LLM 数据诊断**：自动校验（负压/超限/波动异常）+ AI 诊断，SSE 流式输出，支持多轮追问
- **VLM 对话分析**：基于压力曲线图像的视觉语言模型分析，支持多轮对话

### 4. 模型配置管理

- **多模型管理**：通过 UI 增删改模型配置，实时生效，保存至 `models.json`
- **模型连接测试**：一键验证 API Key 与 Base URL 可达性
- **安全脱敏**：API Key 显示为 `****`，保存时保留原值不回写
- **RAG 知识库配置**：配置 iframe URL，保存至 `rag.json`

---

## API 接口参考

### 文件管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload` | 上传试验数据文件到 data/ |
| GET | `/api/files` | 列出 data/ 下所有文件 |
| DELETE | `/api/files/{filename}` | 删除指定文件 |
| PUT | `/api/files/{filename}/rename` | 重命名文件 |

### 数据查询与统计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/data/info?filename=` | 读取文件 header 信息与基本统计 |
| POST | `/api/chart/pressure-curve` | 生成压力-时间曲线 Plotly JSON |
| GET | `/api/chart/channels?filename=` | 获取文件中所有流道相关列的索引 |
| POST | `/api/stats/compute` | 计算所有流道通道的统计值 |

### LLM / VLM 诊断

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/llm/diagnose` | LLM 数据诊断（SSE 流式），支持模型选择与多轮对话 |
| POST | `/api/vlm/chat` | VLM 多轮对话（SSE 流式），支持模型选择 |
| POST | `/api/vlm/analyze-blow` | VLM 流式分析 blow.png |
| POST | `/api/fluent/vlm/analyze` | VLM 分析 CFD 云图（SSE 流式），支持模型选择 |

### RAGflow 通用对话

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ragflow/models` | 获取所有可用模型列表 |
| POST | `/api/ragflow/chat` | 通用聊天（SSE 流式），根据 model_id 路由 |
| POST | `/api/ragflow/test` | 测试模型连接 |

### 模型配置管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/models/config` | 读取 models.json（api_key 脱敏） |
| POST | `/api/models/config` | 保存 models.json |
| POST | `/api/models/test` | 用传入配置直接测试连接 |

### RAG 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/rag/config` | 读取 rag.json |
| POST | `/api/rag/config` | 保存 rag.json |

### Fluent 后处理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/fluent/cases` | 列出所有算例目录 |
| GET | `/api/fluent/case/resolve?case_name=` | 解析算例中的 cas/dat 配对 |
| GET | `/api/fluent/zones?cas_path=` | 解析边界 zone 列表 |
| POST | `/api/fluent/quick-load` | 一键计算入口参数 + 壁面力 |
| POST | `/api/fluent/inlet-only` | 仅计算入口参数 |
| POST | `/api/fluent/wall-forces-only` | 仅计算壁面力 |
| POST | `/api/fluent/symmetry` | 生成对称面云图 |
| POST | `/api/fluent/x-slice/run` | 执行沿程面平均计算 |
| POST | `/api/fluent/x-slice/plot` | 根据已有 CSV 重绘曲线图 |
| POST | `/api/fluent/case/upload` | 上传算例文件并追踪进度 |
| GET | `/api/fluent/case/upload-progress/{job_id}` | SSE 推送算例导入进度 |

---

## 数据格式说明

### 试验数据文件

- **格式**：逗号分隔 txt 文件，UTF-8 编码
- **表头行**：headerIndex = 10（即第 11 行为列名）
- **时间列**：第 0 列（Time (s)）
- **压力列**：由 `A00_parameterData.py` 中的 `S_index` 定义，共 54 个压力传感器通道
- **大气压修正**：所有压力值 +0.101325 MPa

### 传感器布局

| 区域 | 数量 | 轴向位置 (m) |
|------|:---:|------|
| 隔离段上侧 | 15 | 0.05 – 0.80 |
| 一级支板/凹腔燃烧室 | 11 | 0.91 – 1.21 |
| 二级支板/凹腔燃烧室 | 10 | 1.28 – 1.55 |
| 火箭段 | 12 | 1.65 – 2.42 |
| 喷管段 | 6 | 2.54 – 2.84 |

### Fluent HDF5 文件

- **格式**：`.cas.h5`（网格 + 边界拓扑）与 `.dat.h5`（求解结果）
- **读取方式**：h5py 直接解析 `meshes/` 与 `results/` 数据集
- **放置位置**：`Case/<算例名>/` 目录下

---

## 未来规划

### 近期

- 压力异常点检测（3σ / 孤立森林 / LSTM 异常检测）
- 异常检测结果嵌入交互图表（异常点红色标注）
- 自动报告生成（Markdown / PDF）

### 中期

- 多工作流可编排管线（用户自定义分析步骤）
- 多源数据融合分析（传感器 + 高速摄像 + 声学信号）
- 数字孪生对比（实测 vs CFD 自动验证）

### 远期

- 移动端适配与告警推送
- 实时试车数据流接入
- 多 Agent 协作框架（LangChain / AutoGen）
- VLM 本地部署优化
