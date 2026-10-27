# -*- coding: utf-8 -*-
"""唯一路径真源（PROMPT §20.1）。任何脚本都不许自己拼路径，一律 import 本模块。

    from paths import P
    asm   = P.assembly("001")            # 资源库/场景库/H35_沼泽丛林/001_.../mesh/assembly_001.json
    px    = P.px("001", "cover_3")       # 分析/H35_沼泽丛林/001/px_cover_3.json
    aud   = P.audit("001", "cover_3")    # 分析/H35_沼泽丛林/001/audit_cover_3.json
    shot  = P.shot("001", "cover_3")     # 正式产物/场景图/fp_001_cover_3.webp
    slots = P.slots("001")               # dict，该场景 5 个阵位

命令行自检：
    python 工具/paths.py --check         # 16 个场景的件齐不齐，缺件返回非 0
    python 工具/paths.py --list          # 场景清单
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RES = os.path.join(ROOT, "资源库")
LIB = os.path.join(RES, "场景库")
SHARED = os.path.join(RES, "共享依赖")

ANA = os.path.join(ROOT, "分析")

OUT = os.path.join(ROOT, "正式产物")
PAGES = os.path.join(OUT, "页面")
SHOTS = os.path.join(OUT, "场景图")
LISTS = os.path.join(OUT, "清单")

TOOLS = os.path.join(ROOT, "工具")
VIEWER = os.path.join(TOOLS, "viewer")
DOCS = os.path.join(ROOT, "docs")

TMP = os.path.join(ROOT, "临时车间")
LOGDIR = os.path.join(ROOT, "log")
TRASH = os.path.join(ROOT, "回收站")


class UnknownScene(KeyError):
    """未在 registry.json 登记的场景（§20.2 S8 门禁）"""


def _mk(p):
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    return p


def _load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _dump(obj, path):
    _mk(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path


_reg = None


def registry():
    """{arena: {chapter_dir, dir, region, arena, status, updated}}"""
    global _reg
    if _reg is None:
        _reg = (_load(os.path.join(LIB, "registry.json"), {"scenes": {}}) or {}).get("scenes", {})
    return _reg


def scenes():
    return list(registry().keys())


def chapter_dir(arena):
    r = registry().get(arena)
    if not r:
        raise UnknownScene("场景 %r 未在 资源库/场景库/registry.json 登记" % arena)
    return r["chapter_dir"]


def chapter_meta(chapter_dir_name):
    return _load(os.path.join(LIB, chapter_dir_name, "_章节.json"), {}) or {}


def scene_dir(arena):
    r = registry().get(arena)
    if not r:
        raise UnknownScene("场景 %r 未在 资源库/场景库/registry.json 登记" % arena)
    return os.path.join(LIB, r["chapter_dir"], r["dir"])


def source_dir(arena):
    return os.path.join(scene_dir(arena), "source")


def mesh_dir(arena):
    return os.path.join(scene_dir(arena), "mesh")


def tex_dir(arena):
    return os.path.join(scene_dir(arena), "tex")


def card(arena):
    return _load(os.path.join(scene_dir(arena), "场景卡.json"), {}) or {}


def assembly(arena):
    return os.path.join(mesh_dir(arena), "assembly_%s.json" % arena)


def glb(arena):
    return os.path.join(mesh_dir(arena), "arena_%s.glb" % arena)


def meta(arena):
    return os.path.join(mesh_dir(arena), "arena_%s_meta.json" % arena)


def slots_path(arena):
    return os.path.join(mesh_dir(arena), "slots.json")


def slots(arena):
    """该场景的阵位表 {cover_N: {...}}（兼容旧的全局 slots.json[arena] 形态）"""
    d = _load(slots_path(arena), {}) or {}
    return d.get(arena) or (d if "camera_position" not in str(d)[:200] else {})


def views(arena):
    s = slots(arena)
    ks = [k for k in s if k.startswith("cover_")]
    return sorted(ks, key=lambda x: int(x.split("_")[1])) if ks else []


def view(n):
    """3 / "3" / "cover_3" -> "cover_3"（默认 3 号位 = 进图位置）"""
    if isinstance(n, int):
        return "cover_%d" % n
    s = str(n)
    if s.isdigit():
        return "cover_" + s
    return s


def ana_dir(arena):
    return _mk(os.path.join(ANA, chapter_dir(arena), arena, "_"))


def px(arena, v="cover_3"):
    return _mk(os.path.join(ANA, chapter_dir(arena), arena, "px_%s.json" % view(v)))


def audit(arena, v="cover_3"):
    return _mk(os.path.join(ANA, chapter_dir(arena), arena, "audit_%s.json" % view(v)))


def runlog(arena, v="cover_3"):
    return _mk(os.path.join(ANA, chapter_dir(arena), arena, "_run_%s.json" % view(v)))


def ana_shared(name):
    """跨场景的分析中间件（角度分带等）→ 分析/_共享/name"""
    return os.path.join(ANA, "_共享", name)


def shot(arena, v="cover_3"):
    return os.path.join(SHOTS, "fp_%s_%s.webp" % (arena, view(v)))


def shot_png(arena):
    """旧版单张 png（母鲸页仍在用），没有就返回 None"""
    p = os.path.join(SHOTS, "fp_%s.png" % arena)
    return p if os.path.exists(p) else None


def page(name):
    return os.path.join(PAGES, name)


def shared(name):
    return os.path.join(SHARED, name)


def read_json(path, default=None):
    return _load(path, default)


def write_json(obj, path):
    return _dump(obj, path)


# ── 自检 ────────────────────────────────────────────────────────────────
def check(verbose=True):
    """缺件自检。status == '待补' 的场景只提示、不算失败（见 PROMPT §20.2 S3）。

    状态以 registry.json 为准，场景卡不重复写 status。
    """
    reg = registry()
    bad, warn = [], []
    for a in scenes():
        need = [assembly(a), slots_path(a)]
        miss = [os.path.basename(p) for p in need if not os.path.exists(p)]
        if not views(a):
            miss.append("slots(空)")
        if not miss:
            continue
        pending = (reg[a].get("status") == "待补")
        if verbose:
            print("  %s %-7s %-22s 缺 %s%s"
                  % ("~~" if pending else "!!", a, chapter_dir(a), ",".join(miss),
                     "（待补，不阻塞）" if pending else ""))
        (warn if pending else bad).append(a)
    if verbose:
        print("场景 %d / 缺件 %d（其中待补 %d）" % (len(scenes()), len(bad) + len(warn), len(warn)))
        for a in scenes():
            c = card(a)
            m = c.get("mesh") or {}
            print("  %-7s %-16s tris=%-6s hitbox=%-4s covers=%-2s tex=%-4s %s"
                  % (a, chapter_dir(a), m.get("tris"), m.get("hitbox"), m.get("covers"),
                     (c.get("tex") or {}).get("count"), reg[a].get("status")))
    return 0 if not bad else 1


if __name__ == "__main__":
    if "--list" in sys.argv:
        for a in scenes():
            print(a, chapter_dir(a), scene_dir(a))
    else:
        sys.exit(check())
else:
    # 让调用方可以写 `from paths import PATH` 再 `PATH.px(...)`（自引用别名）
    # 注意不要叫 P —— 分析脚本里有同名局部变量（点集数组），会遮蔽
    PATH = sys.modules[__name__]
