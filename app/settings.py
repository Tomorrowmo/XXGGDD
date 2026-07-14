"""统一配置中心 —— 把原先散落、写死在代码里的参数集中到这里，支持环境变量覆盖。

设计目标（对齐 docs/01 §3 写死点清单）：
- 试验解析参数（headerIndex / 分隔符 / 通道命名 / 大气压修正）不再写死在 plotter/A00 里
- 物理常数 γ 统一（修复 symmetry=1.4 vs x_slice=1.3 冲突）
- 判据阈值改为读 sim-knowledge，不写死在 llm_client
- 外部自有资产（simparse / sim-knowledge / SimGraph2）路径可配置

用法：
    from app.settings import settings
    settings.experiment.header_index
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.config import ROOT, DATA_DIR, CASE_DIR


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


def _env_path(key: str, default: Path) -> Path:
    v = os.getenv(key)
    return Path(v) if v else default


# --------------------------------------------------------------------------- #
# 试验数据解析配置（去写死：headerIndex / 分隔符 / 通道正则 / 大气压修正）
# --------------------------------------------------------------------------- #
@dataclass
class ExperimentParseConfig:
    delimiter: str = ","
    encoding: str = "utf-8"
    header_index: int = 10          # 第 11 行是列名（原 A00_parameterData 写死）
    time_column: int = 0            # 时间列固定第 0 列
    # 通道命名正则（原 plotter 只认 "流道\\d+"，现可扩展）
    channel_patterns: list[str] = field(default_factory=lambda: [
        r"流道\d+", r"室压\d+", r"隔离段\d+", r"壁温\d+", r"流量\d+",
    ])
    atmos_correction_mpa: float = 0.101325   # 相对压力→绝对压力（原写死在 plotter:78,151）
    pressure_valid_range_mpa: tuple[float, float] = (0.00001, 10.0)
    max_plot_points: int = 2000     # Plotly 降采样上限


# --------------------------------------------------------------------------- #
# 物理常数（统一，修复原 γ 冲突）
# --------------------------------------------------------------------------- #
@dataclass
class PhysicsConfig:
    gamma: float = 1.4      # 比热比（symmetry 用 1.4、x_slice 曾用 1.3 → 统一为 1.4，可按燃料覆盖）
    gas_constant: float = 287.0


# --------------------------------------------------------------------------- #
# 外部自有资产路径（simparse / sim-knowledge / SimGraph2）
# --------------------------------------------------------------------------- #
@dataclass
class AssetPaths:
    simcli_root: Path = _env_path("SIMCLI_ROOT", Path(r"D:/Git/GitBubProj/simcli"))
    simparse_pkg: Path = _env_path("SIMPARSE_PKG", Path(r"D:/Git/GitBubProj/simcli/sim-parse/src"))
    sim_knowledge: Path = _env_path("SIM_KNOWLEDGE", Path(r"D:/Git/GitBubProj/simcli/sim-knowledge"))
    simgraph2_root: Path = _env_path("SIMGRAPH2_ROOT", Path(r"D:/Git/SimGraph2"))
    # 带 VTK + Romtek 扩展的渲染环境（四切片真实出图走它，子进程调用）
    postprocess_python: Path = _env_path(
        "POSTPROCESS_PYTHON", Path(r"D:/TOOL/Conda/conda/envs/PostProcessTool/python.exe"))

    @property
    def criteria_dir(self) -> Path:
        return self.sim_knowledge / "physics"

    @property
    def mappings_dir(self) -> Path:
        return self.sim_knowledge / "mappings"

    @property
    def labeled_cases_dir(self) -> Path:
        return self.sim_knowledge / "labeled_cases"


# --------------------------------------------------------------------------- #
# LLM / Agent
# --------------------------------------------------------------------------- #
@dataclass
class LLMConfig:
    """大模型配置（对齐 DataAgent：.env 默认 + 运行时 BYOK 覆盖）。"""
    provider: str = _env("LLM_PROVIDER", "deepseek")
    api_key: str = _env("DEEPSEEK_API_KEY", "")
    base_url: str = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    model: str = _env("DEEPSEEK_MODEL", "deepseek-chat")


@dataclass
class AgentConfig:
    vlm_model: str = _env("EVAL_VLM_MODEL", "local/vllm_Qwen2.5-VL-7B")
    cuda_devices: str = _env("EVAL_CUDA", "6,7")   # 本项目固定 cuda:6,7


# --------------------------------------------------------------------------- #
# 顶层配置
# --------------------------------------------------------------------------- #
@dataclass
class Settings:
    db_url: str = _env("EVAL_DB_URL", f"sqlite:///{(ROOT / 'eval_platform.db').as_posix()}")
    data_dir: Path = DATA_DIR                 # 试验上传
    case_dir: Path = CASE_DIR                 # 仿真算例
    ingest_dir: Path = ROOT / "ingest"        # 批量入库暂存
    previews_dir: Path = ROOT / "var" / "previews"   # 切片快照（对齐 SimGraph2 .simgraph/previews）
    reports_dir: Path = ROOT / "var" / "reports"

    llm_config_file: Path = ROOT / "llm_config.json"   # 运行时 BYOK 覆盖存这里
    parse_config_file: Path = ROOT / "parse_config.json"   # 解析/物理常数运行时覆盖

    experiment: ExperimentParseConfig = field(default_factory=ExperimentParseConfig)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    assets: AssetPaths = field(default_factory=AssetPaths)
    agent: AgentConfig = field(default_factory=AgentConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.case_dir, self.ingest_dir,
                  self.previews_dir, self.reports_dir):
            Path(d).mkdir(parents=True, exist_ok=True)


settings = Settings()
