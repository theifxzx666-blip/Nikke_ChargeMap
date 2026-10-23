# -*- coding: utf-8 -*-
"""把指定区域的 5 阵位世界变换合并进 导出/slots.json（不清空已有键）。

用法：
  python build_slots_mw.py <bundle 目录或单文件> <key 前缀>

例：
  python build_slots_mw.py "原始bundle/sbg_mw" mw
  → slots.json["mw001"] / ["mw002"] / ["mw003"]
"""
import json, os, re, sys

from build_slots import build


def main():
    src, prefix = sys.argv[1], sys.argv[2]
    files = [src] if os.path.isfile(src) else [
        os.path.join(src, f) for f in sorted(os.listdir(src)) if f.endswith(".bundle")]
    out_path = os.path.join("导出", "slots.json")
    out = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
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
        out[key] = s
        print("==", key)
        for k in sorted(s):
            e = s[k]
            print("  %-8s root=(%7.2f,%6.2f,%7.2f) yaw=%7.2f  cam=(%7.2f,%6.2f,%7.2f) camYaw=%7.2f" % (
                k, e["root"][0], e["root"][1], e["root"][2], e["root_yaw"],
                e.get("cam", [0, 0, 0])[0], e.get("cam", [0, 0, 0])[1],
                e.get("cam", [0, 0, 0])[2], e.get("cam_yaw", 0)))
    json.dump(out, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("-> 导出/slots.json  键:", ",".join(sorted(out)))


if __name__ == "__main__":
    main()
