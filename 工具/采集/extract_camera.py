# -*- coding: utf-8 -*-
"""提取战斗相机相关 bundle 并 dump 成 JSON（§23 相机实证的数据来源）。

v16（2026-10-28）改造：
  - 不再写死 file_id（那三个是安卓快照的，PC 构建里编号会变），改按 **key 关键字**匹配
  - 支持 PC 客户端本地 store.cdb（不再依赖 adb / 手机）
  - 顺带把每个 bundle 的 typetree dump 成 JSON，脚本类名一并解析

用法：
  # 用 PC 客户端（默认）
  python extract_camera.py
  # 用安卓（adb）
  python extract_camera.py --android

前置（PC 路线）：
  NIKKE_STORE   = <安装目录>/Unity/com_proximabeta_NIKKE/com.shiftup.patch/core/chunk/store.cdb
  NIKKE_CDB_IDX = 同目录 store.cdb.idx（已归档到 采集索引/pc_store.cdb.idx）
  NIKKE_CATALOG = pc catalog 解出来的 sqlite（用 decrypt_nkdb.py 解 catalog.ndb）

输出：
  资源库/共享依赖/引擎件/camera/*.bundle      原始 bundle
  资源库/共享依赖/引擎件/camera/*.json        typetree dump
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import extract_core as EC                                        # noqa: E402

PC = os.environ.get("NIKKE_PC_DIR") or (
    r"E:/[3]Nikke/NIKKEG/Unity/com_proximabeta_NIKKE/com.shiftup.patch")
USE_ANDROID = "--android" in sys.argv

IDX_DIR = os.path.join(ROOT, "资源库", "共享依赖", "采集索引")
OUT = os.path.join(ROOT, "资源库", "共享依赖", "引擎件", "camera")

# 战斗画面里真正决定「看到什么」的四个资产（§23）
PATTERNS = [
    "%spotpresentationbase%spotcameracontrol%",      # Camera + CinemachineBrain + ScopeCameraAttachment
    "%spotpresentationbase%automodecameracontrol%",  # CinemachineTransposer/Composer（自动战斗机位）
    "%spotpresentationbase%arenacamera%",            # 竞技场 vcam
    "%spotpresentationbase%canvas(screenspace-camera)%",
]


def preflight():
    """返回 (catalog, idx, store)，缺项直接给结论。"""
    if USE_ANDROID:
        cat = os.path.join(IDX_DIR, "core_catalog.sqlite")
        idx = os.path.join(IDX_DIR, "core_store.cdb.idx")
        store = os.environ.get("NIKKE_STORE") or (
            "/sdcard/Android/data/com.proximabeta.nikke/files"
            "/com.shiftup.patch/core/chunk/store.cdb")
    else:
        cat = os.path.join(IDX_DIR, "pc_core_catalog.sqlite")
        idx = os.path.join(IDX_DIR, "pc_store.cdb.idx")
        store = os.environ.get("NIKKE_STORE") or os.path.join(PC, "core/chunk/store.cdb")

    bad = []
    if not os.path.exists(cat):
        bad.append("catalog 缺 %s\n    修复：python decrypt_nkdb.py <catalog.ndb> %s" % (cat, cat))
    if not os.path.exists(idx):
        bad.append("cdb.idx 缺 %s\n    修复：拷 store.cdb.idx 到 采集索引/pc_store.cdb.idx" % idx)
    if not os.path.isfile(store) and not USE_ANDROID:
        bad.append("store.cdb 缺 %s\n    修复：设 NIKKE_PC_DIR 或 NIKKE_STORE 指向安装目录" % store)
    return cat, idx, store, bad


def dump_typetree(path, out_json):
    """把 bundle 里全部 MonoBehaviour/Camera/Transform 的 typetree 落 JSON（带脚本类名）。"""
    import UnityPy

    env = UnityPy.load(path)
    scr = {}
    for o in env.objects:
        if o.type.name == "MonoScript":
            try:
                scr[o.path_id] = o.read().m_ClassName
            except Exception:
                pass
    items = []
    for o in env.objects:
        t = o.type.name
        if t not in ("MonoBehaviour", "Camera", "Transform", "GameObject"):
            continue
        try:
            tt = o.read_typetree()
        except Exception as e:
            items.append({"type": t, "pathid": o.path_id, "error": str(e)})
            continue
        if not isinstance(tt, dict):
            continue
        it = {"type": t, "pathid": o.path_id, "name": tt.get("m_Name", "")}
        if t == "MonoBehaviour":
            it["script"] = scr.get((tt.get("m_Script") or {}).get("m_PathID"), "?")
        it["data"] = tt
        items.append(it)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({"file": os.path.basename(path), "items": items}, f,
                  ensure_ascii=False, indent=1)
    return len(items)


def main():
    cat, idx, store, bad = preflight()
    if bad:
        for b in bad:
            print("  !!", b)
        return 1

    EC.CATALOG, EC.IDX_PATH, EC.STORE = cat, idx, store
    print("catalog = %s" % cat)
    print("idx     = %s" % idx)
    print("store   = %s%s" % (store, "  (本地文件)" if os.path.isfile(store) else "  (adb)"))
    EC.load_idx()

    import sqlite3
    con = sqlite3.connect(cat)
    os.makedirs(OUT, exist_ok=True)
    ok = fail = 0
    for pat in PATTERNS:
        rows = list(con.execute(
            "select file_id, key from files_chunktype where key like ? order by file_id", (pat,)))
        if not rows:
            print("MISS 模式无命中: %s" % pat)
            continue
        for fid, key in rows:
            name = os.path.basename(key)
            dst = os.path.join(OUT, name)
            try:
                n, _dbg = EC.extract(fid, dst, con)
                head = open(dst, "rb").read(6)
                assert head[:6] == b"UnityF", "头不是 UnityFS: %r" % head
                ni = dump_typetree(dst, dst[:-7] + ".json")
                print("OK  %-7d %-7d  %-3d obj  %s" % (fid, n, ni, name[:74]))
                ok += 1
            except Exception as e:
                print("ERR %-7d %s  %s" % (fid, e, name[:60]))
                fail += 1
    con.close()
    print("\n完成 %d 个，失败 %d 个 → %s" % (ok, fail, OUT))
    return 0 if not fail else 2


if __name__ == "__main__":
    sys.exit(main())
