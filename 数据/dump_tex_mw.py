# -*- coding: utf-8 -*-
"""导出母鲸领域各战场 bundle 内的贴图（天空盒等），供 viewer 使用。
用法： python dump_tex_mw.py mw001 mw002 mw003
"""
import UnityPy, os, json, sys, glob

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "原始bundle", "sbg_mw")


def dump(key):
    n = key[-3:]
    cands = [p for p in glob.glob(os.path.join(SRC, "*.bundle"))
             if ("motherwhalefield_%s_" % n) in os.path.basename(p)]
    if not cands:
        print("未找到", key); return
    out = os.path.join(BASE, "素材", "tex_" + key)
    os.makedirs(out, exist_ok=True)
    env = UnityPy.load(cands[0])
    idx = []
    for o in env.objects:
        if o.type.name != 'Texture2D':
            continue
        d = o.read()
        try:
            img = d.image
            img.save(os.path.join(out, d.m_Name + ".png"))
            idx.append({"name": d.m_Name, "w": d.m_Width, "h": d.m_Height, "mode": img.mode})
        except Exception as e:
            print("ERR", d.m_Name, e)
    json.dump(idx, open(os.path.join(out, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("%s: %d 张 -> %s" % (key, len(idx), out))
    for it in idx:
        print("   ", it["name"], it["w"], "x", it["h"])


if __name__ == "__main__":
    for a in (sys.argv[1:] or ["mw001"]):
        dump(a)
