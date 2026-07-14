"""可配置试验解析测试：解析/通道分类/统计/阶段分割/稳态取真值。"""
from app.services import experiment as exp


def test_read_and_channels(exp_file):
    parsed = exp.read_experiment(exp_file)
    assert parsed.n_rows == 1000
    labels = [c["label"] for c in parsed.channels]
    assert "流道22" in labels and "室压1" in labels
    cats = {c["label"]: c["category"] for c in parsed.channels}
    assert cats["流道22"] == "流道压力"
    assert cats["室压1"] == "室压"


def test_atmos_correction_in_stats(exp_file):
    parsed = exp.read_experiment(exp_file)
    stats = exp.compute_stats(parsed)
    p22 = next(s for s in stats if s["label"] == "流道22")
    # 主级 ~3.1 相对 + 0.101 修正 → 峰值应 ~3.2
    assert 3.15 < p22["max"] < 3.30


def test_phase_segmentation(exp_file):
    parsed = exp.read_experiment(exp_file)
    ph = exp.segment_phases(parsed)
    # 稳态段应落在 4~16s 附近
    assert ph.steady[0] > 3.0 and ph.steady[1] < 17.0
    assert ph.steady[1] > ph.steady[0]


def test_steady_qoi_extraction(exp_file):
    parsed = exp.read_experiment(exp_file)
    ph = exp.segment_phases(parsed)
    qoi = exp.extract_steady_qoi(parsed, ph)
    assert qoi, "应提取到稳态关键量"
    p22 = next(q for q in qoi if q["quantity"] == "流道22")
    assert p22["unit"] == "MPa"
    assert p22["method"] == "全程峰值"
    room = next(q for q in qoi if q["quantity"] == "室压1")
    assert room["method"] == "稳态段均值"
