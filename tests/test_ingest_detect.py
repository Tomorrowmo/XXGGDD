"""入库类型识别：Fluent/CGNS 目录、传统 .cas/.dat 拒绝、清晰的不支持原因。"""
from pathlib import Path

from app.services.ingest import (
    detect_kind, resolve_case_path, unsupported_reason, CaseKind,
)


def test_cgns_dir_detected_and_resolved(tmp_path):
    (tmp_path / "hb2steady.cgns").write_bytes(b"cgns")
    (tmp_path / "out.cas").write_bytes(b'(0 "fluent"')      # 传统二进制，忽略
    assert detect_kind(tmp_path) == CaseKind.SIMULATION      # 目录含 .cgns → 仿真
    assert resolve_case_path(tmp_path).name == "hb2steady.cgns"


def test_fluent_hdf5_pair_dir(tmp_path):
    (tmp_path / "case.cas.h5").write_bytes(b"\x89HDF")
    (tmp_path / "case.dat.h5").write_bytes(b"\x89HDF")
    assert detect_kind(tmp_path) == CaseKind.SIMULATION
    assert resolve_case_path(tmp_path).name == "case.cas.h5"


def test_legacy_cas_file_rejected(tmp_path):
    f = tmp_path / "out.cas"
    f.write_bytes(b'(0 "fluent"')
    assert detect_kind(f) is None                            # 传统 .cas 二进制不支持
    r = unsupported_reason(f)
    assert ".cas" in r and ("导出" in r or ".cas.h5" in r or ".cgns" in r)


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
