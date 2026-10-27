# -*- coding: utf-8 -*-
"""点位分析工具（PROMPT §20.5 唯一入口）。

读 **场景库** 里的场景资源 → 调分析内核 → 写 **分析/**

    python 工具/分析/analyze.py --list                    列出场景库（含缺件）
    python 工具/分析/analyze.py 001                       默认阵位 cover_3 全流程
    python 工具/分析/analyze.py 001 --view 2              2 号位（也接受 cover_2）
    python 工具/分析/analyze.py all --views 1,2,3,4,5 --jobs 6
    python 工具/分析/analyze.py 001 --stage scan          只跑选点
    python 工具/分析/analyze.py 001 --stage verify        只跑可信度（依赖已有 px）
    python 工具/分析/analyze.py --schema                  只读校验已有产物字段

四个阶段与旧脚本一一对应（可单跑，也可串起来）：
    scan   → scan_px.py     选点（像素级）
    verify → verify_px.py   300 次扰动可信度
    audit  → audit_px.py    六项独立审计 + 容错锥
    rotate → sim_charge.py  战场轮换 / 池子够不够

每组（场景 × 阵位）跑完写一份 `分析/<章节>/<场景>/_run_cover_N.json`：
参数、几何指纹、耗时。几何指纹变了就说明场景重导过，旧点位要重算 ——
`gen_catalog.py --check` 会把这种场景报出来。
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # 工具/
sys.path.insert(0, HERE)                           # 同目录兄弟模块

from paths import PATH                                # noqa: E402

STAGES = ("scan", "verify", "audit", "rotate")
DEFAULTS = {"min_multi": 2, "step": 0.25, "sim": 300, "seed": 20261023,
            "weapon": "SR", "dmg": 10000.0, "limit": 30.0}
TOOL_VERSION = "v14"


def fingerprint(arena):
    """几何指纹：三角面数 + assembly 文件大小。场景重导后必然变化。"""
    p = PATH.assembly(arena)
    if not os.path.exists(p):
        return None
    asm = json.load(open(p, encoding="utf-8"))
    return {"tris": sum(len(x["i"]) // 3 for x in asm["props"]),
            "props": len(asm["props"]),
            "bytes": os.path.getsize(p)}


def run_one(arena, view, stages=STAGES, params=None, force=False, out=print):
    """跑一个（场景 × 阵位）。返回 (ok, info)。可在子进程里调用。"""
    prm = dict(DEFAULTS, **(params or {}))
    v = PATH.view(view)
    t_all = time.time()
    secs = {}
    try:
        if "scan" in stages:
            import scan_px as sp
            t = time.time()
            d = sp.scan(arena, min_multi=prm["min_multi"], step=prm["step"],
                        view=v, occ=True)
            d.setdefault("view", v)
            json.dump(d, open(PATH.px(arena, v), "w", encoding="utf-8"), ensure_ascii=False)
            secs["scan"] = round(time.time() - t, 1)
            out("  scan   %-7s %-8s 点位 %d" % (arena, v, len(d.get("points") or [])))

        if "verify" in stages:
            import verify_px as vp
            t = time.time()
            vp.verify(arena, N=prm["sim"], seed=prm["seed"], view=v)
            secs["verify"] = round(time.time() - t, 1)

        if "audit" in stages:
            import audit_px as ap
            t = time.time()
            ap.audit(arena, view=v)
            secs["audit"] = round(time.time() - t, 1)

        if "rotate" in stages:
            import sim_charge as sc
            t = time.time()
            sc.run([arena], weapon=prm["weapon"], dmg=prm["dmg"],
                   limit=prm["limit"], write=True, view=v)
            secs["rotate"] = round(time.time() - t, 1)

        info = {"scene": arena, "view": v, "params": prm, "stages": list(stages),
                "mesh_fingerprint": fingerprint(arena), "stage_secs": secs,
                "tool_version": TOOL_VERSION,
                "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "secs": round(time.time() - t_all, 1)}
        PATH.write_json(info, PATH.runlog(arena, v))
        n = 0
        if os.path.exists(PATH.px(arena, v)):
            n = len((json.load(open(PATH.px(arena, v), encoding="utf-8")).get("points")) or [])
        out("  done   %-7s %-8s %.0fs 点位 %d" % (arena, v, info["secs"], n))
        return True, info
    except Exception as e:
        out("  FAIL   %-7s %-8s %s: %s" % (arena, v, type(e).__name__, e))
        out(traceback.format_exc(limit=3))
        return False, {"scene": arena, "view": v, "error": str(e)}


def _worker(arg):
    """进程池入口（必须顶层可 pickle）"""
    arena, view, stages, params, force = arg
    return run_one(arena, view, stages, params, force, out=_quiet)


def _quiet(msg):
    print(msg, flush=True)


# ── 子命令 ──────────────────────────────────────────────────────────────
def cmd_list():
    reg = PATH.registry()
    print("%-8s %-16s %-30s %-7s %s" % ("arena", "章节", "目录", "三角面", "status"))
    for a in PATH.scenes():
        c = PATH.card(a)
        m = c.get("mesh") or {}
        print("%-8s %-16s %-30s %-7s %s%s" % (
            a, reg[a]["chapter_dir"], reg[a]["dir"], m.get("tris") or "-",
            c.get("status") or "?",
            "" if PATH.views(a) else "  (缺 slots，无法按阵位分析)"))
    print("\n共 %d 个场景；阵位齐全 %d 个"
          % (len(PATH.scenes()), sum(1 for a in PATH.scenes() if PATH.views(a))))
    return 0


def cmd_schema():
    """只读校验：px 结构 + audit 行数对齐 + 几何指纹是否过期。"""
    bad = 0
    for a in PATH.scenes():
        views = PATH.views(a)
        if not views:
            continue
        fp_now = fingerprint(a)
        for v in views:
            px, au = PATH.px(a, v), PATH.audit(a, v)
            if not os.path.exists(px):
                print("  -- %-7s %-8s 无 px" % (a, v))
                continue
            d = json.load(open(px, encoding="utf-8"))
            miss = [k for k in ("view", "cam", "char", "points", "region")
                    if k not in d]
            n = len(d.get("points") or [])
            if miss:
                print("  !! %-7s %-8s px 缺字段 %s" % (a, v, miss))
                bad += 1
            for i, p in enumerate(d.get("points") or []):
                if not (isinstance(p.get("px"), list) and len(p["px"]) == 2):
                    print("  !! %-7s %-8s 第 %d 点 px 异常 %r" % (a, v, i + 1, p.get("px")))
                    bad += 1
                    break
            if os.path.exists(au):
                rows = json.load(open(au, encoding="utf-8")).get("rows") or []
                if len(rows) != n:
                    print("  !! %-7s %-8s 审计 %d 行 ≠ 点位 %d" % (a, v, len(rows), n))
                    bad += 1
            rl = json.load(open(PATH.runlog(a, v), encoding="utf-8")) \
                if os.path.exists(PATH.runlog(a, v)) else {}
            old_fp = rl.get("mesh_fingerprint")
            if old_fp and fp_now and old_fp.get("tris") != fp_now.get("tris"):
                print("  ?? %-7s %-8s 几何已变（%s → %s 三角面），点位需重算"
                      % (a, v, old_fp.get("tris"), fp_now.get("tris")))
                bad += 1
    print("schema 校验完成，问题 %d 处" % bad)
    return 0 if not bad else 1


def main():
    argv = sys.argv[1:]
    if "--list" in argv:
        return cmd_list()
    if "--schema" in argv or "--verify-schema" in argv:
        return cmd_schema()

    args = []
    stages = list(STAGES)
    views = None
    jobs = 1
    force = False
    params = {}
    it = iter(range(len(argv)))
    i = 0
    while i < len(argv):
        a = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if a == "--stage" and nxt:
            stages = [x for x in nxt.split(",") if x]
            i += 2
            continue
        if a in ("--view", "--views") and nxt:
            views = [x for x in nxt.split(",") if x]
            i += 2
            continue
        if a == "--jobs" and nxt:
            jobs = max(1, int(nxt))
            i += 2
            continue
        if a == "--params" and nxt:
            params = json.loads(nxt)
            i += 2
            continue
        if a.startswith("--stage="):
            stages = [x for x in a.split("=", 1)[1].split(",") if x]
        elif a.startswith("--view="):
            views = [a.split("=", 1)[1]]
        elif a.startswith("--views="):
            views = a.split("=", 1)[1].split(",")
        elif a.startswith("--jobs="):
            jobs = max(1, int(a.split("=", 1)[1]))
        elif a.startswith("--params="):
            params = json.loads(a.split("=", 1)[1])
        elif a == "--force":
            force = True
        elif not a.startswith("--"):
            args.append(a)
        i += 1
    bad = [s for s in stages if s not in STAGES]
    if bad:
        print("未知阶段 %s，可选 %s" % (bad, list(STAGES)))
        return 2

    arg = args[0] if args else "all"
    if arg == "all":
        arenas = PATH.scenes()
    elif arg in PATH.registry():
        arenas = [arg]
    else:
        print("未知场景 %r（用 --list 看可选）" % arg)
        return 2

    plan = []
    for a in arenas:
        vs = views or PATH.views(a) or ["cover_3"]
        for v in vs:
            plan.append((a, PATH.view(v), stages, params, force))

    print("==== %s  场景 %d × 阵位 → %d 组 · 阶段 %s · %d 路 ===="
          % (time.strftime("%H:%M:%S"), len(arenas), len(plan),
             ",".join(stages), jobs))
    t0 = time.time()
    if jobs <= 1:
        res = [run_one(*p) for p in plan]
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            res = list(ex.map(_worker, plan))
    ok = sum(1 for r, _ in res if r)
    fails = [(i.get("scene"), i.get("view")) for r, i in res if not r]
    print("\n成功 %d / %d，用时 %.1f 分钟%s"
          % (ok, len(res), (time.time() - t0) / 60,
             ("，失败 %s" % fails) if fails else ""))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
