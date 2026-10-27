# -*- coding: utf-8 -*-
"""玩家视角 · 单图 5 点 —— 每个战场给出一张实机机位画面 + 5 个最合适充能点。

与 scan_best.py 的区别
----------------------
scan_best.py 求「瞄准空间的理论峰值」，输出的是 yaw/pitch 热力图，机位是战术斜视，
玩家在游戏里看不到。本脚本只回答一个问题：
    **站在阵位上，屏幕上这 5 个地方最值得打。**

相机（全部拆包，非估计）
------------------------
  位置  cover_N.camera_position                      -> 导出/slots.json
  朝向  该 GameObject 旋转 = identity，即沿 +z      -> build_slots.py 实测
  竖直  FOV 60 / near 0.1 / far 300                 -> spotcameracontrol
  换算  character_position 脚底 y=-2.34，相机 y=0   -> 视高 2.34m
  构图  cover_3 相机 (0.6, 0, 0)，角色 (−0.6, −2.34, 4.5)：后撤 4.5m、右偏 1.2m
        角色在画面底部（俯角 27.5°≈画幅下沿），地平线居中 —— 与实机一致

选点口径
--------
  主排序  以该战场**中间阵位 cover_3** 为观察点（画面即此机位）
          取 1° 窗口内不掉段的最优角度（稳瞄），段数高者优先
  去重    角距 ≥ 3°，避免 5 个点挤在同一棵树上
  附带    每个点再用其余 4 个阵位的枪口位置各打一条同角度射线，
          记录各阵位段数 —— 换掩体后这个点值多少，表里直接看

用法
----
  python scan_fp.py all
  python scan_fp.py 001 --sep 3.5
"""
import json, math, os, re, sys

import numpy as np

import scan_best as sb

FP = dict(w=1600, h=900, fov=60.0)

# 画面里的点：世界坐标（Unity 系）由「枪口 + 方向 × 首击距离」给出


def expand(e, key):
    v = e.get(key)
    if isinstance(v, list) and v and isinstance(v[0], list):
        return v[0]
    return v


def slot_origins(slots):
    out = {}
    for k, e in slots.items():
        cp = expand(e, "character_position")
        if not cp:
            continue
        out[k] = np.array([cp[0], cp[1] + sb.GUN_H, cp[2]], dtype=np.float64)
    return out


def scan(arena, sep=4.0, step=0.25, n_pts=12, yaw_rng=None, pitch_rng=None, sep_min=3.0):
    asm = json.load(open(os.path.join("导出", "assembly_%s.json" % arena), encoding="utf-8"))
    slots = json.load(open(os.path.join("导出", "slots.json"), encoding="utf-8"))[arena]
    objs, tri, oi, skipped = sb.load_tris(asm["props"])

    # 扫描范围按区域自适应：swamplandjungle 的可破坏物都在远处、抬 pitch 才够得着；
    # motherwhalefield 有大量负 pitch（物体低于枪口），沿用 (-3,20) 会漏掉 1/3 的目标。
    yaw_rng = yaw_rng or sb.YAW
    pitch_rng = pitch_rng or sb.PITCH
    gy = np.round(np.arange(yaw_rng[0], yaw_rng[1] + 1e-9, step), 4)
    gp = np.round(np.arange(pitch_rng[0], pitch_rng[1] + 1e-9, step), 4)
    orgs = slot_origins(slots)

    # 5 个阵位各算一张覆盖图
    cnts = {}
    for k in sorted(orgs):
        mask, _, _ = sb.build_mask(orgs[k], tri, oi, len(objs), gy, gp, None)
        cnts[k] = mask.sum(axis=0)

    view = "cover_3" if "cover_3" in cnts else sorted(cnts)[0]
    cnt = cnts[view]
    k1 = max(1, int(round(1.0 / step)) | 1)
    e1 = sb.min_filter(cnt, k1)                       # 1° 窗内都至少能到的段数
    names_of = [o["name"] for o in objs]
    # 观察阵位的「稳态覆盖图」：只统计 medium + hard（软质碎掉后仍能穿的段数）
    keep_grp = np.array([o["grp"] in ("medium", "hard") for o in objs])
    # 稳态覆盖图：只把 medium/hard 的 mask 相加。cnts 已经把物体维合并了，所以对 view 重算一次
    _m, _, _ = sb.build_mask(orgs[view], tri, oi, len(objs), gy, gp, None)
    cst = _m[keep_grp].sum(axis=0) if keep_grp.any() else np.zeros_like(cnt)

    def aim_at(P):
        """5 个阵位各自瞄准世界点 P（阵型收敛射击）。

        返回 (五阵位总段数, 各阵位段数, 命中集, 观察阵位的耐久构成)。
        """
        per, names, mix = {}, set(), {"soft": 0, "medium": 0, "hard": 0}
        for k in sorted(orgs):
            v = P - orgs[k]
            yaw = math.degrees(math.atan2(v[0], v[2]))
            pit = math.degrees(math.atan2(v[1], math.hypot(v[0], v[2])))
            hk = sb.exact_hits(orgs[k], yaw, pit, tri, oi, None)
            per[k] = len(hk)
            if k == view:
                names = set(names_of[o] for o, _ in hk)
                for o, _ in hk:
                    mix[objs[o]["grp"]] += 1
        return sum(per.values()), per, names, mix

    # ---- 枚举候选瞄准点：中间阵位的角度栅格 → 首击点 = 玩家实际要点的那个东西
    # 朴素按角距贪心会让 5 个点全落在同一丛树上，故加两道去重：
    #   (a) 与已选点角距 ≥ sep（画面横向 ≈ 17.5px/°，8° ≈ 140px，标签不打架）
    #   (b) 命中目标集合 Jaccard < 0.5（不是同一堆东西）
    #
    # 排序口径（v7）：**稳态段数优先**。
    #   受击点耐久只有三档：soft 100 / medium 500 / hard 1000（ConfigBattleTable）。
    #   软质的一打就碎，碎了就不再充能，所以「首轮 6 段」不等于「每轮 6 段」。
    #   稳态段数 = 命中里 medium + hard 的数量，即软质碎掉之后还能继续穿的段数。
    # ---- 候选池（v9 重写）--------------------------------------------------
    # 旧实现用「按 e1 排序 + 2° 互斥」取 320 格，有两个坑同时踩到：
    #   ① 2° 粗去重是先到先得 —— 旁边的格子先入池，真正要的那个就被跳过；
    #   ② 只按窗口稳健值 e1 排，1° 之外就掉段的「窄峰点」排不进来。
    # 用户反馈的 mw003 yaw−34.5/+5.75 就是被 ① 吃掉的：它在 cst/cnt 上排第 50，
    # 但与先入池的 −33.5/+5.1 只差 1.19°。
    # 现在改为：按 (稳态段) 降序全量枚举（cst>=1），互斥半径降到 0.75°（仅防同格重复），
    # 真正的「画面不重叠」交给后面的 clash()/Jaccard 判据，不再在候选阶段误杀。
    order = np.argsort(-(cst.ravel() * 10 + cnt.ravel()))
    cand, seen_cell = [], 0
    for idx in order:
        j, i = np.unravel_index(int(idx), cst.shape)
        if cst[j, i] < 1:
            continue
        yaw, pit = float(gy[i]), float(gp[j])
        if any(math.hypot(yaw - c["yaw"], pit - c["pitch"]) < 0.75 for c in cand):
            continue
        hits = sb.exact_hits(orgs[view], yaw, pit, tri, oi, None)
        if not hits:
            continue
        _d = sb.ray_dirs(yaw, pit)[0]
        P = orgs[view] + _d * hits[0][1]
        tot, per, names, mix = aim_at(P)
        steady = mix["medium"] + mix["hard"]
        cand.append(dict(yaw=yaw, pitch=pit, n_robust=int(e1[j, i]), n_grid=int(cnt[j, i]),
                         total=tot, per_slot=per, mix=mix, n=sum(mix.values()), n_steady=steady,
                         first=round(float(hits[0][1]), 1),
                         _set=names, _P=P, _d0=len(hits)))
        seen_cell += 1
        if seen_cell >= 4000:
            break

    cand.sort(key=lambda c: (-c["n_steady"], -c["n"], -c["total"]))
    def clash(c, p):
        """两个点能否共存。

        v9 修正：原来只按角距 < sep 一刀切，把「同方位、不同纵深」的两层点误杀。
        典型：mw003 的 yaw−31.0/+5.25（31m，3 段）与 yaw−34.5/+5.86（53m，3 段）
        只差 3.5°，但一个打近处机械、一个打远处管线，命中集合完全不同 —— 两条都该标。

        新判据：
          · 角距 ≥ sep(=4°)        → 可共存（画面 17.5px/°，4° ≈ 70px，46/34px 靶心不重叠）
          · 角距 < sep_min(=3°)    → 一律不共存（3° ≈ 52px，46px 靶心外沿刚好不相交）
          · 3°~4° 之间            → 仅当「首击距离相差 ≥15m」（不同纵深层面）才允许
        """
        dd = math.hypot(c["yaw"] - p["yaw"], c["pitch"] - p["pitch"])
        if dd >= sep:
            return False
        if dd < sep_min:
            return True
        return abs(c.get("first", 0.0) - p.get("first", 0.0)) < 15.0

    pts = []
    for c in cand:
        # 软质全碎的极端点（稳态 0）不入选：首轮好看，第二轮起打它等于空枪
        if c["n_steady"] == 0:
            continue
        if any(clash(c, p) for p in pts):
            continue
        if any(len(c["_set"] & p["_set"]) / max(1, len(c["_set"] | p["_set"])) >= 0.5 for p in pts):
            continue
        pts.append(c)
        if len(pts) >= n_pts:
            break
    if not cand:
        return None

    # ---- 逐点复核：中间阵位取命中清单，5 个阵位各记段数 ------------------
    for n, p in enumerate(pts, 1):
        P = p.pop("_P")
        p.pop("_set", None)
        p.pop("_d0", None)
        hits = sb.exact_hits(orgs[view], p["yaw"], p["pitch"], tri, oi, None)
        p["n"] = len(hits)                       # 中间阵位首轮穿透段数
        p["pct"] = round(p["n"] * sb.PER_SHOT_PCT, 2)
        p["shots"] = int(math.ceil(sb.W_BAR / (p["n"] * sb.CHARGE))) if p["n"] else None
        # 稳态：软质碎掉后仍能穿的段数（medium + hard）
        p["steady_pct"] = round(p["n_steady"] * sb.PER_SHOT_PCT, 2)
        p["steady_shots"] = int(math.ceil(sb.W_BAR / (p["n_steady"] * sb.CHARGE))) if p["n_steady"] else None
        p["first"] = round(hits[0][1], 1) if hits else None
        p["last"] = round(hits[-1][1], 1) if hits else None
        p["detail"] = [dict(name=objs[o]["name"], grp=objs[o]["grp"], hp=objs[o]["hp"],
                            d=round(dd, 1), center=objs[o]["center"]) for o, dd in hits]
        p["squad_pct"] = round(p["total"] * sb.PER_SHOT_PCT, 2)     # 火力聚焦时一轮齐射
        p["squad_shots"] = int(math.ceil(sb.W_BAR / (p["total"] * sb.CHARGE))) if p["total"] else None
        p["no"] = n
        # 特性标签：实战选点的辅助判据（补充点尤其需要，否则只看段数会漏掉更稳的点）
        tags = []
        # 「不掉段」只在区域里存在软质受击点时才是有区分度的标签：
        # motherwhalefield 全域只有 medium/hard，逐点都标等于没标。
        if p["mix"]["soft"] == 0 and any(o["grp"] == "soft" for o in objs):
            tags.append("不掉段")
        if p["n_steady"] >= 3:
            tags.append("高稳态")
        if p["first"] is not None:
            if p["first"] <= 18:
                tags.append("近景")
            elif p["first"] >= 40:
                tags.append("远景")
        if p["per_slot"] and min(p["per_slot"].values()) >= 3:
            tags.append("全阵位")
        if p["n_steady"] == 0:
            tags.append("不值得打")
        p["tags"] = tags
        p["pos"] = [round(float(v), 3) for v in P]                  # 玩家要点的那个点
        p["origin"] = [round(float(v), 3) for v in orgs[view]]
        p["aim"] = [round(float(P[m] - orgs[view][m]), 3) for m in range(3)]

    cam = expand(slots[view], "camera_position")
    char = expand(slots[view], "character_position")
    return dict(arena=arena, view=view, step=step, sep=sep, sep_min=sep_min, n_pts=n_pts,
                region=(re.search(r"sbg_([a-z]+)_\d+", asm.get("arena", "")) or [None, ""])[1],
                scan=dict(yaw=list(yaw_rng), pitch=list(pitch_rng)),
                cam=[round(float(v), 3) for v in cam],
                char=[round(float(v), 3) for v in char],
                fov=FP["fov"], w=FP["w"], h=FP["h"],
                per_shot_pct=sb.PER_SHOT_PCT, energy_per_seg=sb.CHARGE, bar=sb.W_BAR,
                n_hitbox_obj=len(objs), n_tri=len(tri),
                excluded=["cover_object", "static_object", "noncol_object"],
                slots={k: dict(char=[round(float(v), 3) for v in orgs[k]],
                               cam=[round(float(v), 3) for v in expand(slots[k], "camera_position")])
                       for k in orgs},
                points=pts)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sep, n_pts, step, sep_min = 4.0, 12, 0.25, 3.0
    yaw = pitch = None
    for a in sys.argv[1:]:
        if a.startswith("--sep="):
            sep = float(a.split("=")[1])
        if a.startswith("--n="):
            n_pts = int(a.split("=")[1])
        if a.startswith("--sep-min="):
            sep_min = float(a.split("=")[1])
        if a.startswith("--step="):
            step = float(a.split("=")[1])
        if a.startswith("--yaw="):
            yaw = tuple(float(v) for v in a.split("=")[1].split(","))
        if a.startswith("--pitch="):
            pitch = tuple(float(v) for v in a.split("=")[1].split(","))
    arg = args[0] if args else "all"
    if arg == "all":
        arenas = ["001", "002", "003", "004", "005"]
    elif arg == "mw":
        arenas = ["mw001", "mw002", "mw003"]
        yaw = yaw or (-46.0, 46.0)
        pitch = pitch or (-22.0, 22.0)
    else:
        arenas = [arg]
    os.makedirs("render", exist_ok=True)
    for a in arenas:
        d = scan(a, sep, step=step, n_pts=n_pts, yaw_rng=yaw, pitch_rng=pitch, sep_min=sep_min)
        out = os.path.join("导出", "fp_%s.json" % a)
        json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False)
        print("== arena %s  观察点 %s  机位 %s 命中物 %d" % (a, d["view"], d["cam"], d["n_hitbox_obj"]))
        for p in d["points"]:
            per = "/".join(str(p["per_slot"].get("cover_%d" % i, "-")) for i in range(1, 6))
            print("   %d) yaw%+6.2f pitch%+6.2f  首轮%2d段(%4.1f%%) 稳态%2d段(%4.1f%%)  软%d中%d硬%d  首击%5.1fm  聚焦%2d段  各阵位 %s" % (
                p["no"], p["yaw"], p["pitch"], p["n"], p["pct"], p["n_steady"], p["steady_pct"],
                p["mix"]["soft"], p["mix"]["medium"], p["mix"]["hard"], p["first"], p["total"], per))
            for h in p["detail"]:
                print("        - %-46s %s %5.1fm" % (re.sub(r"^sbg_[a-z]+_", "", h["name"]),
                                                     h["grp"][0].upper(), h["d"]))
        print("   ->", out)


if __name__ == "__main__":
    main()
