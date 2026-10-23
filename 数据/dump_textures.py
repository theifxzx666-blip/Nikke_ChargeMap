# -*- coding: utf-8 -*-
"""导出 sbg_swamplandjungle_00N 场景内全部原生素材贴图。

用法： python dump_textures.py 001 002 003 004 005
输出： 素材/tex/         （001 主目录，通用）
       素材/tex_00N/     （各战场独有目录）
"""
import UnityPy, os, json, sys, glob

BASE = os.path.dirname(os.path.abspath(__file__))
BGDIR = os.path.join(BASE, "原始bundle", "bg")


def dump(arena):
    pat = "*sbg_swamplandjungle_%s_*" % arena
    cands = [p for p in glob.glob(os.path.join(BGDIR, "spotbackground(hd)*")) if arena in os.path.basename(p)]
    if not cands:
        print("未找到 %s bundle" % arena)
        return
    out = os.path.join(BASE, "素材", "tex" if arena == "001" else "tex_" + arena)
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
    print("%s: %d 张贴图 -> %s" % (arena, len(idx), out))


if __name__ == "__main__":
    for a in (sys.argv[1:] or ["001"]):
        dump(a)
