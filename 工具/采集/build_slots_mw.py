# -*- coding: utf-8 -*-
"""把指定区域的 5 阵位世界变换写进各场景自己的 mesh/slots.json（v14 起一场景一份）。

用法：
  python build_slots_mw.py <bundle 目录或单文件> <key 前缀>

例：
  python build_slots_mw.py "<bundle 目录>" mw
  → 资源库/场景库/<章节>/mw001_*/mesh/slots.json  的 {"mw001": {cover_N: ...}}
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from paths import PATH                                     # noqa: E402

from build_slots import build


def main():
    src, prefix = sys.argv[1], sys.argv[2]
    files = [src] if os.path.isfile(src) else [
        os.path.join(src, f) for f in sorted(os.listdir(src)) if f.endswith(".bundle")]
    for p in files:
        m = re.search(r"_(\d{3})_[0-9a-f]{32}\.bundle$", p)
        if not m:
            print("skip", p)
            continue
        key = prefix + m.group(1)
        s = build(p)
        if not s:
            print("!! %s 无 cover_* 锚点" % p)
            continue
        print("==", key)
        for k in sorted(s):
            e = s[k]
            print("  %-8s root=(%7.2f,%6.2f,%7.2f) yaw=%7.2f  cam=(%7.2f,%6.2f,%7.2f) camYaw=%7.2f" % (
                k, e["root"][0], e["root"][1], e["root"][2], e["root_yaw"],
                e.get("cam", [0, 0, 0])[0], e.get("cam", [0, 0, 0])[1],
                e.get("cam", [0, 0, 0])[2], e.get("cam_yaw", 0)))
        dst = PATH.slots_path(key)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        cur = json.load(open(dst, encoding="utf-8")) if os.path.exists(dst) else {}
        cur[key] = s
        PATH.write_json(dst, cur)
        print("-> %s" % os.path.relpath(dst, PATH.ROOT))


if __name__ == "__main__":
    main()
