"""
Fluent 后处理 HTTP 路由（APIRouter），供 demo_server / fluent_server 挂载。
project_root 为 FluentAnalysis 项目根（含 app.core.qjz_fluent_post 的目录）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse


def create_fluent_router(project_root: Path) -> APIRouter:
    CASE_DIR = (project_root / "Case").resolve()
    OUTPUT_DIR = (project_root / "output_plots").resolve()
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    router = APIRouter(prefix="/api/fluent", tags=["fluent"])

    def _resolve_path(p: str) -> Path:
        path = Path(p)
        if not path.is_absolute():
            path = (project_root / path).resolve()
        return path

    def _rel_to_root(p: Path) -> str:
        try:
            return p.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            return p.resolve().as_posix()

    def _resolve_case_output_dir(cas_p: Path, case_name: str | None = None) -> Path:
        from app.core.qjz_fluent_post.output_cache import resolve_case_output_dir
        return resolve_case_output_dir(cas_p, CASE_DIR, OUTPUT_DIR, case_name)

    def _case_name_from(body: dict | None = None, *, query: str | None = None) -> str | None:
        raw = query if query is not None else (body or {}).get("case_name", "")
        cn = (raw or "").strip()
        return cn or None

    def _plot_url_in_out_dir(out_dir: Path, png_name: str) -> str:
        try:
            rel = out_dir.resolve().relative_to(CASE_DIR.resolve())
            return "/case_output/" + rel.as_posix() + "/" + png_name
        except ValueError:
            return "/output_plots/" + png_name

    def _symmetry_image_urls(out_dir: Path, filenames: list[str]) -> list[str]:
        try:
            rel = out_dir.resolve().relative_to(CASE_DIR.resolve())
            base = "/case_output/" + rel.as_posix()
        except ValueError:
            base = "/output_plots"
        return [f"{base}/{fn}" for fn in filenames]

    def _symmetry_response(out_dir: Path, section_keys: list[str] | None = None) -> dict:
        from app.core.qjz_fluent_post.output_cache import load_symmetry_sections
        sections = load_symmetry_sections(
            out_dir,
            lambda fns: _symmetry_image_urls(out_dir, fns),
            section_keys=section_keys,
        )
        symmetry_images = next((s["images"] for s in sections if s["key"] == "symmetry"), [])
        return {"sections": sections, "symmetry_images": symmetry_images}

    def _resolve_cas_dat(body: dict) -> tuple[Path, Path, JSONResponse | None]:
        cas_path = body.get("cas_path", "").strip()
        dat_path = body.get("dat_path", "").strip()
        if not cas_path or not dat_path:
            return Path(), Path(), JSONResponse({"error": "缺少 cas_path 或 dat_path"}, status_code=400)
        cas_p = _resolve_path(cas_path)
        dat_p = _resolve_path(dat_path)
        if not cas_p.is_file() or not dat_p.is_file():
            return cas_p, dat_p, JSONResponse({"error": "找不到 cas 或 dat 文件"}, status_code=404)
        return cas_p, dat_p, None

    @router.get("/output/load")
    async def fluent_output_load(cas_path: str, case_name: str = ""):
        """读取算例 Output/ 中已有结果（不重新计算）。"""
        if not cas_path or not cas_path.strip():
            return JSONResponse({"error": "缺少 cas_path"}, status_code=400)
        cas_p = _resolve_path(cas_path.strip())
        if not cas_p.is_file():
            return JSONResponse({"error": f"找不到 cas 文件: {cas_p}"}, status_code=404)
        out_dir = _resolve_case_output_dir(cas_p, _case_name_from(query=case_name))
        from app.core.qjz_fluent_post.output_cache import json_sanitize, load_cached_output
        payload = load_cached_output(
            out_dir,
            lambda fns: _symmetry_image_urls(out_dir, fns),
            lambda name: _plot_url_in_out_dir(out_dir, name),
        )
        payload["cas_path"] = str(cas_p)
        return JSONResponse(json_sanitize(payload))

    @router.get("/output/status")
    async def fluent_output_status(cas_path: str, case_name: str = ""):
        """查询 Output/ 各结果是否已存在。"""
        if not cas_path or not cas_path.strip():
            return JSONResponse({"error": "缺少 cas_path"}, status_code=400)
        cas_p = _resolve_path(cas_path.strip())
        if not cas_p.is_file():
            return JSONResponse({"error": f"找不到 cas 文件: {cas_p}"}, status_code=404)
        out_dir = _resolve_case_output_dir(cas_p, _case_name_from(query=case_name))
        from app.core.qjz_fluent_post.output_cache import output_availability
        return JSONResponse({
            "output_dir": str(out_dir),
            "available": output_availability(out_dir),
        })

    @router.post("/output/clear")
    async def fluent_output_clear(body: dict):
        """清空当前算例 Output/ 中的后处理结果文件。"""
        cas_p, _, err = _resolve_cas_dat(body)
        if err:
            return err
        out_dir = _resolve_case_output_dir(cas_p, _case_name_from(body))
        from app.core.qjz_fluent_post.output_cache import clear_output_dir
        deleted = clear_output_dir(out_dir)
        return JSONResponse({
            "output_dir": str(out_dir),
            "deleted": deleted,
            "count": len(deleted),
        })

    def _safe_case_name(name: str) -> str | None:
        s = (name or "").strip()
        if not s or s in (".", "..") or "/" in s or "\\" in s:
            return None
        return s

    def _pair_cas_dat_in_case_folder(case_folder: Path) -> tuple[list[dict[str, str]], str | None]:
        if not case_folder.is_dir():
            return [], "算例目录不存在"
        cas_files = sorted(case_folder.glob("*.cas.h5"), key=lambda p: p.name.lower())
        dat_files = sorted(case_folder.glob("*.dat.h5"), key=lambda p: p.name.lower())
        dat_by_stem: dict[str, Path] = {}
        for d in dat_files:
            if d.name.endswith(".dat.h5"):
                dat_by_stem[d.name[: -len(".dat.h5")]] = d
        pairs: list[dict[str, str]] = []
        for c in cas_files:
            if not c.name.endswith(".cas.h5"):
                continue
            stem = c.name[: -len(".cas.h5")]
            d = dat_by_stem.get(stem)
            if d and d.is_file():
                pairs.append({
                    "cas_path": _rel_to_root(c),
                    "dat_path": _rel_to_root(d),
                    "label": stem,
                })
        if not pairs and len(cas_files) == 1 and len(dat_files) == 1:
            c, d = cas_files[0], dat_files[0]
            pairs.append({
                "cas_path": _rel_to_root(c),
                "dat_path": _rel_to_root(d),
                "label": c.name[: -len(".cas.h5")],
            })
        if not pairs:
            return [], (
                "未找到可用的 .cas.h5 / .dat.h5 配对；"
                f"当前目录内 cas={len(cas_files)} 个, dat={len(dat_files)} 个"
            )
        return pairs, None

    @router.get("/cases")
    async def fluent_list_cases():
        if not CASE_DIR.is_dir():
            return JSONResponse({
                "exists": False,
                "cases": [],
                "case_root": "Case",
                "message": f"未找到 Case 目录: {CASE_DIR}",
            })
        subs = sorted([p for p in CASE_DIR.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
        cases = [{"name": p.name, "relative": _rel_to_root(p)} for p in subs]
        return JSONResponse({
            "exists": True,
            "cases": cases,
            "case_root": "Case",
            "case_dir_abs": str(CASE_DIR),
        })

    @router.get("/case/resolve")
    async def fluent_resolve_case(case_name: str):
        safe = _safe_case_name(case_name)
        if not safe:
            return JSONResponse({"error": "无效的算例名称"}, status_code=400)
        folder = (CASE_DIR / safe).resolve()
        try:
            folder.relative_to(CASE_DIR.resolve())
        except ValueError:
            return JSONResponse({"error": "路径越界"}, status_code=400)
        pairs, err = _pair_cas_dat_in_case_folder(folder)
        if err:
            return JSONResponse({"error": err, "case_name": safe}, status_code=404)
        primary = pairs[0]
        return JSONResponse({
            "case_name": safe,
            "cas_path": primary["cas_path"],
            "dat_path": primary["dat_path"],
            "pair_label": primary.get("label", ""),
            "pairs": pairs,
        })

    @router.get("/zones")
    async def fluent_zones(cas_path: str):
        if not cas_path or not cas_path.strip():
            return JSONResponse({"error": "缺少 cas_path 查询参数"}, status_code=400)
        cas_p = _resolve_path(cas_path.strip())
        if not cas_p.is_file():
            return JSONResponse({"error": f"找不到 cas 文件: {cas_p}"}, status_code=404)
        try:
            from app.core.qjz_fluent_post.zones import parse_zones
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        zones = parse_zones(str(cas_p))
        type_names = {3: "wall", 7: "symmetry", 4: "pressure-outlet", 2: "velocity-inlet", 1: "interior"}
        out = []
        for z in zones:
            out.append({
                "name": z["name"],
                "type": z["type"],
                "type_label": type_names.get(z["type"], f"type_{z['type']}"),
                "n_faces": z["n_faces"],
                "min_fid": z["min_fid"],
                "max_fid": z["max_fid"],
            })
        return JSONResponse({"zones": out, "cas_path": str(cas_p)})

    @router.post("/quick-load")
    async def fluent_quick_load(body: dict):
        """入口参数 + 壁面力；优先读取 Output 缓存，force=true 时强制重算。"""
        cas_p, dat_p, err = _resolve_cas_dat(body)
        if err:
            return err
        from app.core.qjz_fluent_post.output_cache import json_sanitize, parse_force_flag, parse_inlet_report_txt, parse_wall_forces_txt
        force = parse_force_flag(body.get("force", False))
        out_dir = _resolve_case_output_dir(cas_p, _case_name_from(body))
        from app.core.qjz_fluent_post.zones import parse_zones
        from app.core.qjz_fluent_post.wall_forces import (
            compute_wall_forces,
            save_wall_forces_report_txt,
            wall_forces_to_serializable,
        )
        from app.core.qjz_fluent_post.inlet_conditions import compute_inlet_report, save_inlet_report_txt

        from_cache: list[str] = []
        try:
            zones = parse_zones(str(cas_p))
            inlets = None if force else parse_inlet_report_txt(out_dir / "inlet_parameters.txt")
            payload = None if force else parse_wall_forces_txt(out_dir / "wall_forces.txt")

            if inlets is None:
                inlets = compute_inlet_report(str(cas_p), str(dat_p))
                save_inlet_report_txt(
                    str(out_dir / "inlet_parameters.txt"), inlets,
                    cas_file=str(cas_p), dat_file=str(dat_p),
                )
            else:
                from_cache.append("inlet")

            if payload is None:
                wall_raw = compute_wall_forces(str(cas_p), str(dat_p))
                payload = wall_forces_to_serializable(wall_raw)
                save_wall_forces_report_txt(
                    str(out_dir / "wall_forces.txt"), payload,
                    cas_file=str(cas_p), dat_file=str(dat_p),
                )
            else:
                from_cache.append("wall")
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        return JSONResponse(json_sanitize({
            **payload,
            "inlets": inlets,
            "zones": [{"name": z["name"], "type": z["type"], "n_faces": z["n_faces"]} for z in zones],
            "output_dir": str(out_dir),
            "cas_path": str(cas_p),
            "dat_path": str(dat_p),
            "from_cache": from_cache,
        }))

    @router.post("/inlet-only")
    async def fluent_inlet_only(body: dict):
        cas_p, dat_p, err = _resolve_cas_dat(body)
        if err:
            return err
        from app.core.qjz_fluent_post.output_cache import json_sanitize, parse_force_flag, parse_inlet_report_txt
        force = parse_force_flag(body.get("force", False))
        out_dir = _resolve_case_output_dir(cas_p, _case_name_from(body))
        from app.core.qjz_fluent_post.inlet_conditions import compute_inlet_report, save_inlet_report_txt
        try:
            inlets = None if force else parse_inlet_report_txt(out_dir / "inlet_parameters.txt")
            from_cache = inlets is not None
            if inlets is None:
                inlets = compute_inlet_report(str(cas_p), str(dat_p))
                save_inlet_report_txt(
                    str(out_dir / "inlet_parameters.txt"), inlets,
                    cas_file=str(cas_p), dat_file=str(dat_p),
                )
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        return JSONResponse(json_sanitize({"inlets": inlets, "output_dir": str(out_dir), "from_cache": from_cache}))

    @router.post("/wall-forces-only")
    async def fluent_wall_only(body: dict):
        cas_p, dat_p, err = _resolve_cas_dat(body)
        if err:
            return err
        from app.core.qjz_fluent_post.output_cache import json_sanitize, parse_force_flag, parse_wall_forces_txt
        force = parse_force_flag(body.get("force", False))
        out_dir = _resolve_case_output_dir(cas_p, _case_name_from(body))
        from app.core.qjz_fluent_post.wall_forces import (
            compute_wall_forces,
            save_wall_forces_report_txt,
            wall_forces_to_serializable,
        )
        try:
            payload = None if force else parse_wall_forces_txt(out_dir / "wall_forces.txt")
            from_cache = payload is not None
            if payload is None:
                wall_raw = compute_wall_forces(str(cas_p), str(dat_p))
                payload = wall_forces_to_serializable(wall_raw)
                save_wall_forces_report_txt(
                    str(out_dir / "wall_forces.txt"), payload,
                    cas_file=str(cas_p), dat_file=str(dat_p),
                )
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        return JSONResponse(json_sanitize({**payload, "output_dir": str(out_dir), "from_cache": from_cache}))

    @router.post("/symmetry")
    async def fluent_symmetry(body: dict):
        """生成单个截面云图；优先读取 Output 缓存。"""
        cas_p, dat_p, err = _resolve_cas_dat(body)
        if err:
            return err
        section = (body.get("section") or "").strip().lower()
        if section not in ("symmetry", "xy", "xz"):
            return JSONResponse({"error": "section 须为 symmetry、xy 或 xz"}, status_code=400)
        from app.core.qjz_fluent_post.output_cache import parse_force_flag, section_pngs_complete
        force = parse_force_flag(body.get("force", False))
        out_dir = _resolve_case_output_dir(cas_p, _case_name_from(body))
        from_cache = False
        try:
            if not force and section_pngs_complete(out_dir, section):
                from_cache = True
            else:
                from app.core.qjz_fluent_post.symmetry_plot import plot_symmetry
                plot_symmetry(str(cas_p), str(dat_p), str(out_dir), sections=[section])
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        sym_data = _symmetry_response(out_dir, section_keys=[section])
        if not sym_data["sections"]:
            return JSONResponse({"error": f"截面 {section} 未生成任何云图"}, status_code=500)
        return JSONResponse({
            **sym_data,
            "section": section,
            "from_cache": from_cache,
            "output_dir": str(out_dir),
            "cas_path": str(cas_p),
            "dat_path": str(dat_p),
        })

    @router.post("/x-slice/run")
    async def fluent_x_slice_run(body: dict):
        """沿程面平均；优先读取 Output 缓存，force=true 时强制重算。"""
        cas_p, dat_p, err = _resolve_cas_dat(body)
        if err:
            return err
        from app.core.qjz_fluent_post.output_cache import (
            XSLICE_CSV,
            XSLICE_META,
            build_x_slice_meta_from_csv,
            parse_force_flag,
        )
        force = parse_force_flag(body.get("force", False))
        n_slices = int(body.get("n_slices", 100) or 100)
        out_dir = _resolve_case_output_dir(cas_p, _case_name_from(body))
        from app.core.qjz_fluent_post.x_slice_average import plot_x_slice_field, run_x_slice_analysis, x_slice_plot_filename
        csv_path = out_dir / XSLICE_CSV
        from_cache = False
        try:
            if not force and csv_path.is_file():
                from_cache = True
                meta_path = out_dir / XSLICE_META
                if meta_path.is_file():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                else:
                    meta = build_x_slice_meta_from_csv(csv_path)
            else:
                csv_path, meta = run_x_slice_analysis(
                    str(cas_p), str(dat_p), str(out_dir), n_slices=max(10, min(n_slices, 500)),
                )
                csv_path = Path(csv_path)
                meta_path = out_dir / XSLICE_META
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

            first_key = meta["fields"][0]["key"] if meta["fields"] else "P_static"
            png_name = x_slice_plot_filename(first_key)
            png_path = out_dir / png_name
            if not png_path.is_file():
                plot_x_slice_field(
                    str(csv_path),
                    first_key,
                    str(png_path),
                    x_min_mm=None,
                    x_max_mm=None,
                    y_min=None,
                    y_max=None,
                )
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        plot_url = _plot_url_in_out_dir(out_dir, png_name)
        return JSONResponse({
            "csv_path": str(csv_path),
            "meta": meta,
            "plot_url": plot_url,
            "plot_filename": png_name,
            "output_dir": str(out_dir),
            "from_cache": from_cache,
        })

    @router.post("/x-slice/plot")
    async def fluent_x_slice_plot(body: dict):
        """根据已有 CSV 重绘单张 PNG（较快）。"""
        cas_path = body.get("cas_path", "").strip()
        dat_path = body.get("dat_path", "").strip()
        field = (body.get("field") or "P_static").strip()
        cas_p = _resolve_path(cas_path)
        dat_p = _resolve_path(dat_path)
        if not cas_p.is_file() or not dat_p.is_file():
            return JSONResponse({"error": "找不到 cas 或 dat 文件"}, status_code=404)
        out_dir = _resolve_case_output_dir(cas_p, _case_name_from(body))
        csv_path = out_dir / "x_slice_averaged.csv"
        if not csv_path.is_file():
            return JSONResponse({"error": "请先执行沿程面平均计算生成 CSV"}, status_code=400)

        def _f(name: str):
            v = body.get(name)
            if v is None or v == "":
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        x_min_mm = _f("x_min_mm")
        x_max_mm = _f("x_max_mm")
        y_min = _f("y_min")
        y_max = _f("y_max")

        try:
            from app.core.qjz_fluent_post.x_slice_average import plot_x_slice_field, x_slice_plot_filename
            png_name = x_slice_plot_filename(field)
            png_path = out_dir / png_name
            plot_x_slice_field(
                str(csv_path),
                field,
                str(png_path),
                x_min_mm=x_min_mm,
                x_max_mm=x_max_mm,
                y_min=y_min,
                y_max=y_max,
            )
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        try:
            rel = out_dir.resolve().relative_to(CASE_DIR.resolve())
            plot_url = "/case_output/" + rel.as_posix() + "/" + png_name
        except ValueError:
            plot_url = "/output_plots/" + png_name
        return JSONResponse({"plot_url": plot_url, "plot_filename": png_name, "field": field, "output_dir": str(out_dir)})

    @router.post("/case/upload")
    async def fluent_case_upload(
        case_name: str = Form(...),
        files: list[UploadFile] = File(...),
    ):
        """
        上传 .cas.h5 / .dat.h5 到 Case/<算例名>/。
        返回 job_id，通过 GET /case/upload-progress/{job_id}（SSE）查看写入 Case 目录进度。
        """
        from .local_case_upload import (
            create_upload_job,
            run_import_in_background,
            validate_case_name,
            validate_upload_filename,
        )

        try:
            safe = validate_case_name(case_name)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

        if not files:
            return JSONResponse({"error": "未选择文件"}, status_code=400)

        file_items: list[tuple[str, bytes]] = []
        try:
            for uf in files:
                raw_name = uf.filename or ""
                content = await uf.read()
                if not content:
                    return JSONResponse({"error": f"文件为空: {raw_name}"}, status_code=400)
                file_items.append((validate_upload_filename(raw_name), content))
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

        case_dest = CASE_DIR / safe
        if case_dest.exists() and any(case_dest.iterdir()):
            return JSONResponse(
                {"error": f"算例目录已存在且非空: Case/{safe}，请更换名称或清空目录"},
                status_code=409,
            )

        job_id = create_upload_job()
        run_import_in_background(CASE_DIR, safe, file_items, job_id)
        total_bytes = sum(len(b) for _, b in file_items)
        return JSONResponse({
            "job_id": job_id,
            "case_name": safe,
            "total_bytes": total_bytes,
            "file_count": len(file_items),
            "filenames": [n for n, _ in file_items],
        })

    @router.get("/case/upload-progress/{job_id}")
    async def fluent_case_upload_progress(job_id: str):
        """SSE：推送算例导入进度（写入本机 Case 目录）。"""
        from .local_case_upload import get_upload_job

        async def event_stream():
            while True:
                job = get_upload_job(job_id)
                if not job:
                    yield f"data: {json.dumps({'error': '任务不存在', 'done': True})}\n\n"
                    break
                payload = {
                    "percent": job.get("percent", 0),
                    "message": job.get("message", ""),
                    "status": job.get("status", "pending"),
                    "error": job.get("error"),
                    "case_name": job.get("case_name"),
                    "files": job.get("files", []),
                    "done": job.get("status") in ("done", "error"),
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                if payload["done"]:
                    break
                await asyncio.sleep(0.35)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
