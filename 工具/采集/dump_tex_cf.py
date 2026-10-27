# -*- coding: utf-8 -*-
"""导出 sbg_cityforestundercrystal_00N（第 35 章）场景内全部原生贴图。
用法： python dump_tex_cf.py c001 c002 ...
输出： 资源库/共享依赖/素材/tex_c00N/   （v14 起；gitignore）
"""
import UnityPy, os, json, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import PATH                                     # noqa: E402
BASE = PATH.ROOT                                    # 工位根
SHARED = os.path.join(PATH.RES, "共享依赖")          # 采集中间物落这里（gitignore）
TMP  = os.path.join(SHARED, "原始bundle")
SRC = os.path.join(TMP, "sbg_cf")


def dump(key):
    n = key[1:]
    p = os.path.join(SRC, "sbg_cityforestundercrystal_%s.bundle" % n)
    out = os.path.join(SHARED, "素材", "tex_" + key)
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
