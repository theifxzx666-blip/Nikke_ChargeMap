# -*- coding: utf-8 -*-
"""提取 spotbackground(hd) 系列背景 bundle（游戏实机背景的原生素材）。

复用 extract_core.py 的链路，IDX 指向本目录下的 core_store.cdb.idx。
用法： python extract_spot_bg.py 23466 23467 ...
"""
import sqlite3, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_core as E

E.CATALOG = r"F:\Codex\Nikke\Nikke_Skills\拆包\04_临时车间\国际服采集_20261022\catalog\core_catalog.sqlite"
E.IDX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core_store.cdb.idx")

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "原始bundle", "bg")

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    con = sqlite3.connect(E.CATALOG)
    E.load_idx()
    ids = [int(x) for x in sys.argv[1:]]
    for fid in ids:
        row = con.execute("select key from files_chunktype where file_id=?", (fid,)).fetchone()
        if not row:
            print("ERR %d 无 key" % fid); continue
        name = os.path.basename(row[0])
        path = os.path.join(OUT, name)
        try:
            n, dbg = E.extract(fid, path, con)
            head = open(path, "rb").read(6)
            print("OK  %-7d %-9d %-6s %s" % (fid, n, head.decode("ascii", "replace"), name[:80]), flush=True)
        except Exception as e:
            print("ERR %-7d %s  %s" % (fid, e, name[:60]), flush=True)
    con.close()
