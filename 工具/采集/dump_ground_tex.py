# -*- coding: utf-8 -*-
"""补导出地面贴图（ground_*_c）到场景的 tex/。

为什么单独写：dump_tex.py 按「材质实例引用」导出，而 ground_* 只是**材质名引用**、
不在实例列表里，所以 112 个场景里有 61 个的 tex/ 缺 ground 贴图。
后果：export_glb 的 ground_tile() 找不到图 → 地面无纹理（c003 直接白成一片）。

用法：
  python dump_ground_tex.py            # 补全库缺失的
  python dump_ground_tex.py c003 001   # 只补指定场景
  python dump_ground_tex.py --check    # 只报告缺哪些
"""
import json
import os
import sys

import UnityPy
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
from paths import PATH                                       # noqa: E402
import glob


def main(argv):
    check = "--check" in argv
    only = [a for a in argv if not a.startswith("-")]
    reg = json.load(open(os.path.join(ROOT, "资源库", "场景库", "registry.json"), encoding="utf-8"))["scenes"]
    done = skipped = 0
    for a in sorted(reg):
        if only and a not in only:
            continue
        r = reg[a]
        d = os.path.join(ROOT, "资源库", "场景库", r["chapter_dir"], r["dir"])
        texdir = os.path.join(d, "tex")
        src = glob.glob(os.path.join(d, "source", "*.bundle"))
        if not src:
            continue
        if os.path.isdir(texdir) and any("ground" in f.lower() and f.endswith(".png")
                                         for f in os.listdir(texdir)):
            skipped += 1
            continue
        env = UnityPy.load(src[0])
        got = []
        for o in env.objects:
            if o.type.name != "Texture2D":
                continue
            try:
                t = o.read_typetree()
            except Exception:
                continue
            name = t.get("m_Name", "")
            if "ground" not in name.lower():
                continue
            if check:
                got.append(name); continue
            try:
                im = o.read().image
            except Exception:
                continue
            os.makedirs(texdir, exist_ok=True)
            im.save(os.path.join(texdir, name + ".png"))
            got.append(name)
        if got:
            done += 1
            print("%-16s %s %s" % (a, "缺" if check else "补", ", ".join(got[:3])))
    print("\n%s %d 个场景（已有 %d 个跳过）" % ("缺贴图" if check else "已补", done, skipped))


if __name__ == "__main__":
    main(sys.argv[1:])
