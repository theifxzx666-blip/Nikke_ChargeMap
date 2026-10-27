# -*- coding: utf-8 -*-
"""按场景名提取 spotbackground(hd) 战斗场景 bundle。

用法：
  python extract_sbg_cf.py cityforestundercrystal
  python extract_sbg_cf.py cityforestunder <自定义输出目录>

默认输出： 资源库/共享依赖/原始bundle/sbg_<前两位>/   （v14 起；整目录 gitignore）
拿到 bundle 后手工移进对应场景目录的 source/，并在 场景卡.json 的 source 段登记 sha1。

只取 `spotbackground(hd)_assets_sbg_<名字>_<3位编号>_<hash>.bundle`，
自动排除 `_rightclear` / `_midclear` 之类的清除变体（它们编号后面多一段后缀）。
"""
import os
import re
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import extract_core as ec

CAT = r"F:\Codex\Nikke\Nikke_Skills\拆包\04_临时车间\国际服采集_20261022\catalog\core_catalog.sqlite"


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "cityforestundercrystal"
    out = (sys.argv[2] if len(sys.argv) > 2
           else os.path.join(ROOT, "资源库", "共享依赖", "原始bundle", "sbg_" + name[:2]))
    os.makedirs(out, exist_ok=True)

    pat = re.compile(r"^spotbackground\(hd\)_assets_(sbg_%s_\d{3})_[0-9a-f]{32}\.bundle$" % re.escape(name))
    con = sqlite3.connect(CAT)
    ec.load_idx()

    want = []
    for fid, key in con.execute(
            "select file_id, key from files_chunktype where key like ? order by key",
            ("%sbg_%s_%" % ("%", name),)):
        m = pat.match(key.split("/")[-1])
        if m:
            want.append((fid, m.group(1)))
    print("命中 hd 主场景:", len(want), flush=True)
    for fid, key in want:
        dst = os.path.join(out, key + ".bundle")
        n, dbg = ec.extract(fid, dst, con)
        print("OK %-32s %10d bytes  head=%s  %s"
              % (key, n, open(dst, "rb").read(6).decode("ascii", "replace"), dbg[:1]), flush=True)
    con.close()


if __name__ == "__main__":
    main()
