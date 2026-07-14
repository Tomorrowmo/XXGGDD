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
    for sc in [scalar, "T", "Mach", "p", "U", "rho"]:
        try:
            SR.render_case(mb, sc, out_dir)
            imgs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(out_dir, "*.png")))
            if imgs:
                return {"ok": True, "scalar": sc, "images": imgs, "engine": "vendored-vtk"}
        except Exception:
            continue
    return {"ok": False, "error": "渲染未产出图像", "engine": "vendored-vtk"}


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
        for sc in [scalar, "T", "Mach", "p", "U", "rho"]:
            try:
                SR.render_case(mb, sc, out_dir)
                imgs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(out_dir, "*.png")))
                if imgs:
                    return {"ok": True, "scalar": sc, "images": imgs, "engine": "simgraph2-romtek"}
            except Exception:
                continue
        return {"ok": False, "error": "渲染未产出图像"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"渲染异常：{e}"}


def main() -> None:
    if len(sys.argv) < 3:
        _emit({"ok": False, "error": "usage: render_runner.py <case> <out> [scalar]"})
        return
    case_path, out_dir = sys.argv[1], sys.argv[2]
    scalar = sys.argv[3] if len(sys.argv) > 3 else "T"
    os.makedirs(out_dir, exist_ok=True)
    try:
        if _is_openfoam(case_path):
            _emit(_render_openfoam(case_path, out_dir, scalar))
        else:
            _emit(_render_via_simgraph2(case_path, out_dir, scalar))
    except Exception as e:  # noqa: BLE001
        _emit({"ok": False, "error": f"渲染失败：{e}"})


if __name__ == "__main__":
    main()
