# -*- coding: utf-8 -*-
"""把某个场景 bundle 里的全部 Texture2D 导进**该场景自己的 `tex/`**。

v15 起取代 `dump_textures.py` / `dump_tex_cf.py` / `dump_tex_mw.py` 三个硬编码脚本。
关键简化：贴图的归属不需要额外破解 —— **从哪个 bundle 导出来的就属于哪个场景**，
直接落 `PATH.tex_dir(arena)`（= `资源库/场景库/<章节>/<场景>/tex/`），符合 §20.2 S7。

用法：
  python dump_tex.py <arena> [更多 arena…]
  python dump_tex.py --bundle <某个.bundle> --out <输出目录>       # 脱离 registry 单独跑

输出：
  <场景>/tex/<贴图原名>.png   （名字保留客户端原名，不重命名）
  <场景>/tex/index.json       （name / w / h / mode，供 export_glb 与查看器用）
"""
import glob
import json
import os
import sys

import UnityPy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from paths import PATH, UnknownScene                        # noqa: E402


def dump_bundle(bundle, outdir, quiet=False):
    os.makedirs(outdir, exist_ok=True)
    env = UnityPy.load(bundle)
    idx, err = [], 0
    for o in env.objects:
        if o.type.name != "Texture2D":
            continue
        d = o.read()
        try:
            img = d.image
            img.save(os.path.join(outdir, d.m_Name + ".png"))
            idx.append({"name": d.m_Name, "w": d.m_Width, "h": d.m_Height, "mode": img.mode})
        except Exception as e:
            err += 1
            if not quiet:
                print("  ERR %s %s" % (d.m_Name, e))
    json.dump(idx, open(os.path.join(outdir, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return len(idx), err


def dump_arena(arena, quiet=False):
    """从场景 source/ 里挑主 bundle 导贴图。"""
    sd = PATH.source_dir(arena)
    cands = sorted(glob.glob(os.path.join(sd, "*.bundle")))
    if not cands:
        raise RuntimeError("%s 的 source/ 里没有 bundle" % arena)
    # 有多份时优先挑与 scene 卡 sha1_16 对得上的那份；否则取最大的（主场景包通常最大）
    want = set(s.get("sha1_16", "") for s in (PATH.card(arena).get("source") or []))
    want.discard("")
    pick = None
    if want:
        import hashlib
        for p in cands:
            h = hashlib.sha1(open(p, "rb").read()).hexdigest()[:16]
            if h in want:
                pick = p
                break
    if pick is None:
        pick = max(cands, key=os.path.getsize)
    n, err = dump_bundle(pick, PATH.tex_dir(arena), quiet=quiet)
    if not quiet:
        print("  %-8s tex=%d  err=%d  <- %s" % (arena, n, err, os.path.basename(pick)))
    return n, err


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--bundle":
        if len(argv) < 4 or argv[2] != "--out":
            print("用法: python dump_tex.py --bundle <x.bundle> --out <dir>")
            return 2
        n, err = dump_bundle(argv[1], argv[3])
        print("tex=%d err=%d -> %s" % (n, err, argv[3]))
        return 0
    bad = 0
    for a in argv:
        try:
            dump_arena(a)
        except UnknownScene:
            print("  !! %s 未在 registry 登记（§20.2 S8）" % a)
            bad += 1
        except Exception as e:
            print("  ERR %s %s" % (a, e))
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
