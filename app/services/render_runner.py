"""切片渲染子进程脚本 —— 由任意装了 VTK 的 python 运行。

OpenFOAM：走平台自有的 vendored 渲染（app/services/render/*），**不依赖 SimGraph2 仓库**，
          平台基础环境（VTK 9.6+）即可出图。
其它格式（Fluent .cas.h5 等需 Romtek）：回退到 SimGraph2/PostEngine（需 SIMGRAPH2_ROOT +
          带 Romtek 的 PostProcessTool 环境）；不可用则诚实报错。

用法：  <python> render_runner.py <case_path> <out_dir> [scalar]
输出：  stdout 最后一行是 JSON：{"ok":bool, "scalar":..., "images":[...], "engine":..., "error":...}
"""
import sys
import os
import glob
import json


def _emit(d):
    print(json.dumps(d, ensure_ascii=False))


# 标量优先级：马赫 > 温度 > 压力系数 > 压力 > 密度 > 速度分量 > 其它（用真实存在的场名，避免黑白网格）
_SCALAR_PREFER = [
    ("mach", 0), ("temperature", 1), ("^t$|^temp", 1),
    ("coefpressure|^cp$|pressurecoef", 2), ("pressure|^p$", 3),
    ("density|^rho$", 4), ("velocitymag|^umag|velocity|^u", 5),
]


def _rank(name: str) -> int:
    import re
    low = (name or "").lower()
    for pat, r in _SCALAR_PREFER:
        if re.search(pat, low):
            return r
    return 99


def _detect_scalars(mb) -> list:
    """扫 multiblock 里真实存在的单分量标量场，按物理意义优先级排序。

    避免写死 ['T','Mach',...] 在不同学科算例（气动 CGNS 用 Density/Pressure/Mach，
    燃烧 OpenFOAM 用 T）上找不到场→渲成无色网格。
    """
    found: dict[str, int] = {}
    for i in range(mb.GetNumberOfBlocks()):
        b = mb.GetBlock(i)
        if b is None:
            continue
        for getter in (getattr(b, "GetPointData", None), getattr(b, "GetCellData", None)):
            if getter is None:
                continue
            pd = getter()
            for a in range(pd.GetNumberOfArrays()):
                arr = pd.GetArray(a)
                if arr is None or arr.GetNumberOfComponents() != 1:
                    continue
                nm = pd.GetArrayName(a)
                if nm and nm not in found:
                    found[nm] = _rank(nm)
    return sorted(found, key=lambda k: (found[k], k))


_GENERIC = {"t", "mach", "p", "u", "rho"}


def _scalar_candidates(mb, preferred: str) -> list:
    """尝试顺序：数据里真实存在的场（按物理优先级）优先 → 用户指定 → 常见名兜底。

    真实存在的场放最前，避免 render_case 用一个不存在的名（如默认 'T'）渲成无色网格却"成功"。
    """
    detected = _detect_scalars(mb)
    order = []
    # 若 preferred 是具体（非泛用默认名）且存在于数据，优先它
    if preferred and preferred.lower() not in _GENERIC and preferred in detected:
        order.append(preferred)
    for s in detected + [preferred, "T", "Mach", "p", "U", "rho"]:
        if s and s not in order:
            order.append(s)
    return order


def _is_openfoam(case_path: str) -> bool:
    if case_path.lower().endswith(".foam"):
        return True
    if os.path.isdir(case_path):
        return (os.path.exists(os.path.join(case_path, "system", "controlDict"))
                or bool(glob.glob(os.path.join(case_path, "*.foam"))))
    return False


def _render_openfoam(case_path: str, out_dir: str, scalar: str) -> dict:
    """平台自有渲染：vendored openfoam_loader + simagent_render（无 SimGraph2/Romtek）。"""
    # 让本脚本能 import 平台的 render 包（app/services/render）
    here = os.path.dirname(os.path.abspath(__file__))          # app/services
    sys.path.insert(0, here)
    from render import openfoam_loader, simagent_render as SR   # type: ignore

    if case_path.lower().endswith(".foam"):
        case_path = os.path.dirname(case_path)
    mb = openfoam_loader.load_openfoam(case_path)
    for sc in _scalar_candidates(mb, scalar):
        try:
            SR.render_case(mb, sc, out_dir)
            _make_thumb(SR, mb, out_dir)
            imgs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(out_dir, "*.png")))
            if imgs:
                return {"ok": True, "scalar": sc, "images": imgs, "engine": "vendored-vtk"}
        except Exception:
            continue
    return {"ok": False, "error": "渲染未产出图像", "engine": "vendored-vtk"}


def _make_thumb(vendored_sr, mb, out_dir) -> None:
    """生成 thumb.png（能认出模型外形）。失败静默——切片本身已产出。"""
    try:
        vendored_sr.render_thumbnail(mb, os.path.join(out_dir, "thumb.png"))
    except Exception:
        pass


def _vendored_render():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    from render import simagent_render as VSR  # type: ignore
    return VSR


def _render_via_simgraph2(case_path: str, out_dir: str, scalar: str) -> dict:
    """回退：需 Romtek 的格式走 SimGraph2/PostEngine（需 SIMGRAPH2_ROOT + Romtek 环境）。"""
    sg2 = os.environ.get("SIMGRAPH2_ROOT", r"D:/Git/SimGraph2")
    if not os.path.isdir(sg2):
        return {"ok": False, "error": f"该格式需 Romtek 渲染，但 SIMGRAPH2_ROOT 不可用：{sg2}"}
    sys.path.insert(0, sg2)
    try:
        os.chdir(sg2)
    except Exception:
        pass
    try:
        from post_engine.engine import PostEngine
        import simagent_render as SR
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"import SimGraph2/Romtek 失败：{e}"}
    try:
        eng = PostEngine()
        sid = "render"
        r = eng.load_file(sid, case_path)
        if isinstance(r, dict) and r.get("error"):
            return {"ok": False, "error": r["error"]}
        mb = eng.session_mgr.get(sid).post_data.get_vtk_data()
        vsr = _vendored_render()  # 缩略图用平台自有渲染（与加载引擎无关）
        for sc in _scalar_candidates(mb, scalar):
            try:
                SR.render_case(mb, sc, out_dir)
                _make_thumb(vsr, mb, out_dir)
                imgs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(out_dir, "*.png")))
                if imgs:
                    return {"ok": True, "scalar": sc, "images": imgs, "engine": "simgraph2-romtek"}
            except Exception:
                continue
        return {"ok": False, "error": "渲染未产出图像"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"渲染异常：{e}"}


def _load_mb(case_path: str):
    """加载算例为 VTK multiblock（OpenFOAM 用 vendored；否则 Romtek），返回 (mb, engine)。"""
    if _is_openfoam(case_path):
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        from render import openfoam_loader  # type: ignore
        cp = os.path.dirname(case_path) if case_path.lower().endswith(".foam") else case_path
        return openfoam_loader.load_openfoam(cp), "vendored-vtk"
    sg2 = os.environ.get("SIMGRAPH2_ROOT", r"D:/Git/SimGraph2")
    if not os.path.isdir(sg2):
        raise RuntimeError(f"该格式需 Romtek，但 SIMGRAPH2_ROOT 不可用：{sg2}")
    sys.path.insert(0, sg2)
    try:
        os.chdir(sg2)
    except Exception:
        pass
    from post_engine.engine import PostEngine  # type: ignore
    eng = PostEngine()
    r = eng.load_file("render", case_path)
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError(r["error"])
    return eng.session_mgr.get("render").post_data.get_vtk_data(), "simgraph2-romtek"


def _render_turntable(case_path: str, out_dir: str, n_frames: int) -> dict:
    """绕轴 n 帧（供前端拖拽轨道旋转）；缩略图渲染始终用平台自有 vendored 代码。"""
    try:
        mb, engine = _load_mb(case_path)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}
    vsr = _vendored_render()
    try:
        n = vsr.render_turntable(mb, out_dir, n_frames=n_frames)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"turntable 渲染失败：{e}"}
    if not n:
        return {"ok": False, "error": "未挑到可渲染的物面"}
    imgs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(out_dir, "turn_*.png")))
    return {"ok": True, "images": imgs, "frames": len(imgs), "engine": engine, "mode": "turntable"}


def main() -> None:
    if len(sys.argv) < 3:
        _emit({"ok": False, "error": "usage: render_runner.py <case> <out> [scalar|mode]"})
        return
    case_path, out_dir = sys.argv[1], sys.argv[2]
    arg3 = sys.argv[3] if len(sys.argv) > 3 else "T"
    os.makedirs(out_dir, exist_ok=True)
    try:
        if arg3.startswith("turntable"):     # turntable:24
            n = 24
            if ":" in arg3:
                try:
                    n = max(6, min(48, int(arg3.split(":", 1)[1])))
                except ValueError:
                    n = 24
            _emit(_render_turntable(case_path, out_dir, n))
        elif _is_openfoam(case_path):
            _emit(_render_openfoam(case_path, out_dir, arg3))
        else:
            _emit(_render_via_simgraph2(case_path, out_dir, arg3))
    except Exception as e:  # noqa: BLE001
        _emit({"ok": False, "error": f"渲染失败：{e}"})


if __name__ == "__main__":
    main()
