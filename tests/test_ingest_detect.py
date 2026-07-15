"""入库类型识别：Fluent/CGNS 目录、传统 .cas/.dat 拒绝、清晰的不支持原因。"""
from pathlib import Path

from app.services.ingest import (
    detect_kind, resolve_case_path, unsupported_reason, CaseKind,
)


def test_cgns_preferred_over_legacy_cas(tmp_path):
    (tmp_path / "hb2steady.cgns").write_bytes(b"cgns")
    (tmp_path / "out.cas").write_bytes(b'(0 "fluent"')      # 传统 .cas 也支持，但 CGNS 优先(渲染更稳)
    assert detect_kind(tmp_path) == CaseKind.SIMULATION
    assert resolve_case_path(tmp_path).name == "hb2steady.cgns"


def test_fluent_hdf5_pair_dir(tmp_path):
    (tmp_path / "case.cas.h5").write_bytes(b"\x89HDF")
    (tmp_path / "case.dat.h5").write_bytes(b"\x89HDF")
    assert detect_kind(tmp_path) == CaseKind.SIMULATION
    assert resolve_case_path(tmp_path).name == "case.cas.h5"   # HDF5 最优先


def test_fluent_legacy_cas_supported(tmp_path):
    # simparse 支持 Fluent 传统 .cas —— 应识别为仿真，不再拒绝
    f = tmp_path / "out.cas"
    f.write_bytes(b'(0 "fluent"')
    assert detect_kind(f) == CaseKind.SIMULATION
    # 只有 .cas（无 cgns）的目录 → 解析到该 .cas
    (tmp_path / "out.dat").write_bytes(b'(0 "fluent"')
    assert resolve_case_path(tmp_path).name == "out.cas"


def test_dat_alone_reason(tmp_path):
    f = tmp_path / "out.dat"
    f.write_bytes(b"x")
    assert detect_kind(f) is None
    assert ".cas" in unsupported_reason(f)


def test_parent_dir_only_subdirs_reason(tmp_path):
    (tmp_path / "sub").mkdir()
    assert detect_kind(tmp_path) is None
    r = unsupported_reason(tmp_path)
    assert "批量目录扫描" in r or "子目录" in r


def test_openfoam_dir_still_uses_dir(tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "controlDict").write_text("app icoFoam;", encoding="utf-8")
    assert detect_kind(tmp_path) == CaseKind.SIMULATION
    assert resolve_case_path(tmp_path) == tmp_path           # OpenFOAM 仍用目录本身
