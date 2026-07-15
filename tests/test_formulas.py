"""公式库（skills）测试 —— 用解析算例校验，确保提取的公式与物理一致。"""
import numpy as np
import pytest

from app.services import formulas as F
from app.services.formulas import compressible as C
from app.services.formulas import forces, geometry, averaging, flow, experiment


# --------------------------------------------------------------- 可压缩流（解析值）
def test_isentropic_M2_gamma14():
    # M=2, γ=1.4 的教科书标准值：T0/T=1.8，P0/p=7.824
    assert C.total_temperature(300.0, 2.0, gamma=1.4) == pytest.approx(300 * 1.8, rel=1e-6)
    assert C.total_pressure(1e5, 2.0, gamma=1.4) == pytest.approx(1e5 * 7.82445, rel=1e-4)


def test_speed_of_sound_and_mach():
    # a=sqrt(γp/ρ); 对 γ=1.4, p=101325, ρ=1.225 → a≈340.3 m/s
    a = float(C.speed_of_sound(101325.0, 1.225, gamma=1.4))
    assert a == pytest.approx(340.3, abs=1.0)
    m = float(C.mach_number(340.3, 101325.0, 1.225, gamma=1.4))
    assert m == pytest.approx(1.0, abs=0.01)


def test_dynamic_pressure_and_velmag():
    assert float(C.dynamic_pressure(1.225, 100.0)) == pytest.approx(0.5 * 1.225 * 1e4)
    assert float(C.velocity_magnitude(3.0, 4.0)) == pytest.approx(5.0)          # 2D
    assert float(C.velocity_magnitude(1.0, 2.0, 2.0)) == pytest.approx(3.0)     # 3D


def test_gamma_defaults_to_settings():
    from app.settings import settings
    # 不传 γ 时用 settings.physics.gamma
    expect = C.total_temperature(300.0, 1.0, gamma=settings.physics.gamma)
    assert C.total_temperature(300.0, 1.0) == pytest.approx(expect)


# --------------------------------------------------------------- 几何（单位正方形）
def test_polygon_area_normal_unit_square():
    sq = [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]  # xy 平面单位正方形
    area, n = geometry.polygon_area_normal(sq)
    assert area == pytest.approx(1.0)
    assert abs(n[2]) == pytest.approx(1.0)   # 法向沿 ±z
    assert geometry.polygon_area_normal([[0, 0, 0], [1, 1, 1]])[0] == 0.0  # 退化


# --------------------------------------------------------------- 力（单面）
def test_pressure_force_single_face():
    # 单位面积、外法向 +x、压力 100Pa → 压力力 = 100·(-x)·1 = (-100,0,0)
    fp = forces.pressure_force([100.0], [[1, 0, 0]], [1.0])
    assert fp == pytest.approx([-100.0, 0.0, 0.0])


def test_viscous_and_total_force():
    fv = forces.viscous_force([[1, 0, 0], [2, 0, 0]])
    assert fv == pytest.approx([3.0, 0.0, 0.0])
    ft = forces.total_force([100.0], [[1, 0, 0]], [1.0], [[5, 0, 0]])
    assert ft == pytest.approx([-95.0, 0.0, 0.0])


def test_force_coefficient():
    # F=100, ½ρV²A = ½·1·10²·1 = 50 → C=2
    assert forces.force_coefficient(100.0, 1.0, 10.0, 1.0) == pytest.approx(2.0)
    assert forces.force_coefficient(1.0, 0.0, 0.0, 0.0) == 0.0  # 防 0 除


# --------------------------------------------------------------- 平均
def test_slice_average_linear():
    # field = x → 每层均值≈层中心 x
    x = np.linspace(0, 10, 1001)
    pos, avg = averaging.slice_average(x, x, n_slices=5)
    assert pos[0] == pytest.approx(0.0) and pos[-1] == pytest.approx(10.0)
    # 单调递增；中间层(x≈5)均值≈5；边缘层因半层无数据而略偏内
    assert np.all(np.diff(avg) > 0)
    assert avg[2] == pytest.approx(5.0, abs=0.2)


def test_area_and_mass_weighted():
    assert averaging.area_weighted_average([1.0, 3.0], [1.0, 3.0]) == pytest.approx((1 + 9) / 4)
    assert averaging.mass_weighted_average([1.0, 3.0], [1.0, 1.0]) == pytest.approx(2.0)


# --------------------------------------------------------------- 流量
def test_mass_flow():
    assert flow.mass_flow_from_flux([1.0, 2.0, 3.0]) == pytest.approx(-6.0)   # Fluent 取负
    # ρ=1, V=(1,0,0), n=(1,0,0), A=2 → ṁ=2
    assert flow.mass_flow_general([1.0], [[1, 0, 0]], [[1, 0, 0]], [2.0]) == pytest.approx(2.0)
    assert flow.boundary_mean([1.0, 2.0, np.nan, 3.0]) == pytest.approx(2.0)


# --------------------------------------------------------------- 试验
def test_experiment_formulas():
    assert float(experiment.atmos_correct(1.0, 0.101325)) == pytest.approx(1.101325)
    assert experiment.coefficient_of_variation([10, 10, 10]) == pytest.approx(0.0)
    assert experiment.relative_deviation_pct(11.0, 10.0) == pytest.approx(10.0)


# --------------------------------------------------------------- 目录
def test_catalog_complete_and_public():
    assert len(F.CATALOG) >= 14
    for item in F.CATALOG:
        assert callable(item["fn"])
        assert item["key"] and item["expr"] and item["category"]
    from app.services.formulas.catalog import catalog_public
    pub = catalog_public()
    assert all("fn" not in it for it in pub)   # 可 JSON 化
    import json
    json.dumps(pub, ensure_ascii=False)         # 不抛错
