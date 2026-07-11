"""解析 Fluent HDF5 网格中的 zone（边界）拓扑与名称。"""

from __future__ import annotations

import h5py

# Fluent zoneType 常见取值（与 test_qjz 一致）
FLUENT_ZONE_TYPE_WALL = 3
FLUENT_ZONE_TYPE_SYMMETRY = 7


def parse_zones(cas_file: str):
    """
    读取 .cas.h5 中 meshes/1/faces/zoneTopology，返回每个 zone 的字典列表。

    每个元素包含：idx, id, name, type, min_fid, max_fid, n_faces
    其中 min_fid / max_fid 为 Fluent 1-based、max 为包含端点。
    """
    with h5py.File(cas_file, "r") as f:
        zt = f["meshes/1/faces/zoneTopology"]
        zone_ids = zt["id"][:]
        ztypes = zt["zoneType"][:]
        min_ids = zt["minId"][:]
        max_ids = zt["maxId"][:]

        raw = zt["name"][0]
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        parts = [s.strip() for s in raw.replace(";", "\x00").split("\x00") if s.strip()]
        n = len(zone_ids)
        if len(parts) >= n:
            names = parts[-n:]
        else:
            names = parts + [f"zone_{zone_ids[i]}" for i in range(len(parts), n)]

    zones = []
    for i in range(n):
        zones.append({
            "idx": i,
            "id": int(zone_ids[i]),
            "name": names[i],
            "type": int(ztypes[i]),
            "min_fid": int(min_ids[i]),
            "max_fid": int(max_ids[i]),
            "n_faces": int(max_ids[i]) - int(min_ids[i]) + 1,
        })
    return zones
