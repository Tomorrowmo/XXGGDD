"""服务器文件浏览端点测试（/fs/list）—— 目录导航 + 可入库项识别。"""


def _mk_tree(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "note.md").write_text("x", encoding="utf-8")           # 不可入库
    (tmp_path / "run.txt").write_text("t", encoding="utf-8")           # 试验可入库
    (tmp_path / "mesh.cgns").write_bytes(b"cgns")                       # 仿真可入库
    case = tmp_path / "ofcase"
    (case / "system").mkdir(parents=True)
    (case / "system" / "controlDict").write_text("app icoFoam;", encoding="utf-8")  # OpenFOAM 目录
    return tmp_path


def test_fs_list_dir_and_ingestable(client, tmp_path):
    _mk_tree(tmp_path)
    d = client.get("/api/v2/fs/list", params={"path": str(tmp_path)}).json()
    by = {e["name"]: e for e in d["entries"]}
    assert by["run.txt"]["ingestable"] is True and by["run.txt"]["kind"] == "experiment"
    assert by["mesh.cgns"]["ingestable"] is True and by["mesh.cgns"]["kind"] == "simulation"
    assert by["note.md"]["ingestable"] is False
    assert by["ofcase"]["is_dir"] is True and by["ofcase"]["ingestable"] is True  # OpenFOAM 目录
    assert by["sub"]["is_dir"] is True and by["sub"]["ingestable"] is False
    assert d["parent"] == str(tmp_path.parent).replace("\\", "/")


def test_fs_list_empty_returns_drives(client):
    d = client.get("/api/v2/fs/list").json()
    assert d["drives"]  # 至少一个盘符/根
    assert d["entries"]  # 空路径列出盘符


def test_fs_list_missing_path_404(client):
    r = client.get("/api/v2/fs/list", params={"path": "Z:/definitely/not/here/xyz"})
    assert r.status_code == 404


def test_fs_list_file_returns_parent_dir(client, tmp_path):
    _mk_tree(tmp_path)
    f = tmp_path / "run.txt"
    d = client.get("/api/v2/fs/list", params={"path": str(f)}).json()
    # 传文件 → 返回其所在目录
    assert d["path"] == str(tmp_path).replace("\\", "/")
