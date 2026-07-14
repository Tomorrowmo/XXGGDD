"""切片渲染子进程脚本 —— 由 PostProcessTool 环境的 python 运行（含 VTK+Romtek）。

不 import 本项目任何模块（PostProcessTool 环境没有本项目依赖）；只用 stdlib + SimGraph2。
用法：  <PostProcessTool python> render_runner.py <case_path> <out_dir> [scalar]
输出：  stdout 最后一行是 JSON：{"ok":bool, "scalar":..., "images":[...], "error":...}
环境：  SIMGRAPH2_ROOT 指向 SimGraph2 根。
"""
import sys
import os
import glob
import json


def main() -> None:
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "usage: render_runner.py <case> <out> [scalar]"}))
        return
    case_path = sys.argv[1]
    out_dir = sys.argv[2]
    scalar = sys.argv[3] if len(sys.argv) > 3 else "T"

    sg2 = os.environ.get("SIMGRAPH2_ROOT", r"D:/Git/SimGraph2")
    sys.path.insert(0, sg2)
    try:
        os.chdir(sg2)
    except Exception:
        pass

    # OpenFOAM 传目录：.foam 文件 → 其父目录
    if case_path.lower().endswith(".foam"):
        case_path = os.path.dirname(case_path)

    os.makedirs(out_dir, exist_ok=True)
    try:
        from post_engine.engine import PostEngine
        import simagent_render as SR
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"import SimGraph2 失败: {e}"}))
        return

    try:
        eng = PostEngine()
        sid = "render"
        r = eng.load_file(sid, case_path)
        if isinstance(r, dict) and r.get("error"):
            print(json.dumps({"ok": False, "error": r["error"]}))
            return
        mb = eng.session_mgr.get(sid).post_data.get_vtk_data()
        for sc in [scalar, "T", "Mach", "p", "U", "rho"]:
            try:
                SR.render_case(mb, sc, out_dir)
                imgs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(out_dir, "*.png")))
                if imgs:
                    print(json.dumps({"ok": True, "scalar": sc, "images": imgs}))
                    return
            except Exception:
                continue
        print(json.dumps({"ok": False, "error": "渲染未产出图像"}))
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"渲染异常: {e}"}))


if __name__ == "__main__":
    main()
