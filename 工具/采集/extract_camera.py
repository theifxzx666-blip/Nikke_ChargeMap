# -*- coding: utf-8 -*-
"""定点提取相机相关 bundle（复用 extract_core 的链路）。

输出： 资源库/共享依赖/引擎件/camera/   （v14 起）
索引： 工具/采集/core_store.cdb.idx
"""
import sys, os, sqlite3
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import extract_core as EC

EC.IDX_PATH = os.path.join(HERE, "core_store.cdb.idx")
EC.load_idx()

OUT = os.path.join(ROOT, "资源库", "共享依赖", "引擎件", "camera")
os.makedirs(OUT, exist_ok=True)

CON = sqlite3.connect(EC.CATALOG)
for fid in (24709, 14923, 25647):
    row = CON.execute("select key from files_chunktype where file_id=?", (fid,)).fetchone()
    if not row:
        print("MISS", fid); continue
    name = os.path.basename(row[0])
    path = os.path.join(OUT, name)
    try:
        n, dbg = EC.extract(fid, path, CON)
        print("OK  %-6d %-9d %s" % (fid, n, name[:80]))
    except Exception as e:
        print("ERR %-6d %s  %s" % (fid, e, name[:60]))
CON.close()
