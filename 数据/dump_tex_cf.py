# -*- coding: utf-8 -*-
"""导出 sbg_cityforestundercrystal_00N（第 35 章）场景内全部原生贴图。
用法： python dump_tex_cf.py c001 c002 ...
输出： 素材/tex_c00N/
"""
import UnityPy, os, json, sys

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "原始bundle", "sbg_cf")


def dump(key):
    n = key[1:]
    p = os.path.join(SRC, "sbg_cityforestundercrystal_%s.bundle" % n)
    out = os.path.join(BASE, "素材", "tex_" + key)
    os.makedirs(out, exist_ok=True)
    env = UnityPy.load(p)
    idx = []
    for o in env.objects:
        if o.type.name != "Texture2D":
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
    print("%s: %d 张贴图 -> %s" % (key, len(idx), os.path.basename(out)), flush=True)


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["c001"]):
        dump(k)
