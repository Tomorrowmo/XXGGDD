"""判据服务测试：偏差分级、评级、试验异常规则。"""
from app.services.criteria import (
    tier_from_deviation, grade_from_avg_deviation, check_experiment_anomalies,
)


def test_deviation_tiers():
    assert tier_from_deviation(2.0) == "优秀"
    assert tier_from_deviation(4.0) == "合格"
    assert tier_from_deviation(8.0) == "需复核"
    assert tier_from_deviation(15.0) == "不合格"


def test_grade_thresholds():
    assert grade_from_avg_deviation(1.2, True) == "A"
    assert grade_from_avg_deviation(1.8) == "A-"
    assert grade_from_avg_deviation(3.0) == "B+"
    assert grade_from_avg_deviation(9.0) == "C+"
    assert grade_from_avg_deviation(20.0) == "C"


def test_anomaly_negative_pressure():
    stats = [{"label": "流道22", "category": "流道压力", "min": -0.5, "max": 3.0, "mean": 2.0, "std": 0.3}]
    hits = check_experiment_anomalies(stats)
    assert any(h.intent == "is_negative_pressure" for h in hits)


def test_anomaly_over_range():
    stats = [{"label": "流道22", "category": "流道压力", "min": 0.1, "max": 12.0, "mean": 6.0, "std": 0.3}]
    hits = check_experiment_anomalies(stats)
    assert any(h.intent == "is_over_range" for h in hits)


def test_anomaly_fluctuation():
    stats = [{"label": "室压1", "category": "室压", "min": 0.1, "max": 3.0, "mean": 0.5, "std": 1.5}]
    hits = check_experiment_anomalies(stats)
    assert any(h.intent == "is_excessive_fluctuation" for h in hits)


def test_no_false_anomaly_on_good_data():
    stats = [{"label": "流道22", "category": "流道压力", "min": 0.11, "max": 3.2, "mean": 2.9, "std": 0.3}]
    assert check_experiment_anomalies(stats) == []
