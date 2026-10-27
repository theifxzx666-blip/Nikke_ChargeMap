# -*- coding: utf-8 -*-
"""点位独立审计（v12）—— 不信任原链路，从头复算一遍

为什么要有这一层
----------------
`scan_px.py` 出点、`verify_px.py` 打分，两者共用同一套假设：
相机在 `camera_position`、朝向 identity、FOV 60、角色站阵位中心、枪口 1.45m。
`verify_px.py` 的蒙特卡洛只是在这套假设周围抖一抖 —— **如果假设本身是错的，
抖得再多次也不会发现错误，只会给错误一个漂亮的可信度**。

所以审计换一套问法，六项互相独立：

  A 往返自洽    px → 射线 → 世界点 → 投影回 px，误差必须 < 0.5px。
                这一项查代码，不查假设。任何 >1px 说明投影/反投影不自洽（写错了）。
  B 容错锥      从**枪口**出发（不经过相机），在 yaw/pitch 上四方向扫，
                找「稳态段数开始掉」的边界。这是**相机无关**的指标 ——
                它只依赖枪口位置和场景几何，不受相机标定影响。
                和 scan 的支撑半径 `rad` 应该吻合；差太多说明有 bug。
  C 阵位一致性  5 个阵位各自重算。玩家不会正好站 cover_3。
                取最弱阵位作为真实下限，而不是「全阵位都行」的一句话。
  D 俯角全域    meta 里写得很清楚：`position/pitch 由运行时 Cinemachine 驱动`。
                也就是说俯角是**唯一没有实证**的参数。这里扫 −6°..+6°，
                看段数在哪个俯角下开始崩 —— 崩得早 = 这一点依赖「相机恰好没俯角」。
  E 宽高比      玩家屏幕不是 1600×900。NIKKE 手机 20:9、模拟器 16:10/21:9 都常见。
                纵向 FOV 固定（多数 TPS 做法）时，横向像素坐标会整体偏移。
                偏移 > 50px（NMS 冲突阈值）意味着**同一颗红点在别人屏幕上指别处**。
  F 可辨识度    首击物体投影到屏幕上的包围盒有多大。8×6px 的物体在手机上
                玩家根本认不出来 —— 这是「照图打不准」最朴素的原因。

用法
----
  python audit_px.py 001
  python audit_px.py all
  python audit_px.py all --top=8      # 只审前 8 个点（快）
"""
import json, math, os, sys, time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import PATH                                     # noqa: E402
import charge_core as sb                          # noqa: E402
import scan_px as sp
import verify_px as vp

W, H, FOV = sp.W, sp.H, sp.FOV
BLK_OBJS = (None, None)                      # (遮挡体名字表, 三角面→物体索引)


# ---------------------------------------------------------------- 基础工具
def load_arena(arena):
    global BLK_OBJS
    asm = json.load(open(PATH.assembly(arena), encoding="utf-8"))
    props = asm["props"]
    objs, tri, oi, _ = sp.load_props([p for p in props if p.get("g") in sb.HITBOX], set(sb.HITBOX))
    blk_objs, tri_b, bi_b, _ = sp.load_props(
        [p for p in props if p.get("g") in sp.BLOCK_GROUPS or p.get("g") == "cover_object"],
        set(sp.BLOCK_GROUPS) | {"cover_object"})
    BLK_OBJS = (blk_objs, bi_b)
    _, tri_cover, _, _ = sp.load_props(
        [p for p in props if p.get("g") == "cover_object"], {"cover_object"})
    _, tri_all, _, _ = sp.load_props(
        [p for p in props if p.get("g") in sp.SOLID_GROUPS and p.get("g") != "cover_object"],
        set(sp.SOLID_GROUPS) - {"cover_object"})
    steady = [o["grp"] in ("medium", "hard") for o in objs]
    return props, objs, tri, oi, tri_b, tri_cover, tri_all, steady


def count_at(org, yaw, pit, tri, oi, tri_b, steady):
    """枪口角度 → (总段数, 稳态段数)。含遮挡截断。返回 (0,0) 表示没打到。"""
    hits = sb.exact_hits(org, yaw, pit, tri, oi, None)
    if not hits:
        return 0, 0
    bd = sp.blocker_dist(org, yaw, pit, tri_b)
    if math.isfinite(bd):
        hits = [(o, d) for o, d in hits if d < bd]
    if not hits:
        return 0, 0
    return len(hits), sum(1 for o, _ in hits if steady[o])


# ---------------------------------------------------------------- A 往返自洽
def audit_roundtrip(d, cam, char):
    """px → 射线 → 世界点 → 投影回 px。"""
    tw, tc, th, asp = vp.cam_basis(FOV)
    out = []
    for p in d["points"]:
        u, v = p["px"]
        dvec = vp.pix_dir(u, v, tw, th, asp)
        out.append(dict(no=p["no"], px=[round(u, 1), round(v, 1)], P=p["pos"]))
        # 用命中点反投影
        pr = vp.project(np.array(p["pos"], float), cam, tc, th, asp)
        if pr is None:
            out[-1]["err"] = None
        else:
            out[-1]["err"] = round(float(math.hypot(pr[0] - u, pr[1] - v)), 2)
        # 用射线自洽：沿 dvec 走到 p["pos"] 的投影长度，再看落点偏差
        P = np.array(p["pos"], float)
        t = float(np.dot(P - cam, dvec))
        Pc = cam + dvec * t
        out[-1]["perp"] = round(float(np.linalg.norm(P - Pc)), 3)   # 命中点到射线的垂距 (m)
    errs = [o["err"] for o in out if o["err"] is not None]
    perps = [o["perp"] for o in out]
    return dict(per_point=out,
                err_med=round(float(np.median(errs)), 2) if errs else None,
                err_max=round(float(max(errs)), 2) if errs else None,
                perp_med=round(float(np.median(perps)), 3) if perps else None,
                perp_max=round(float(max(perps)), 3) if perps else None,
                ok=bool(errs and max(errs) < 1.0))


# ---------------------------------------------------------------- B 容错锥
def audit_cone(p, org, tri, oi, tri_b, steady, step=0.02, dmax=6.0):
    """四方向扫，找稳态段数掉到标称以下的最大偏移（度）。相机无关。

    返回 yaw/pitch 两个方向的容错（取正负方向较小值），并换算成像素。
    """
    nom = p["n_steady"]
    y0, p0 = p["yaw"], p["pitch"]
    if nom <= 0:
        return None

    def edge(axis, sgn):
        lo, hi = 0.0, dmax
        # 先确认 dmax 处是否还成立；都成立就报 dmax（饱和）
        a, b = (y0 + sgn * dmax, p0) if axis == 0 else (y0, p0 + sgn * dmax)
        if count_at(org, a, b, tri, oi, tri_b, steady)[1] >= nom:
            return dmax
        for _ in range(60):                       # 二分到 0.005°
            mid = 0.5 * (lo + hi)
            a, b = (y0 + sgn * mid, p0) if axis == 0 else (y0, p0 + sgn * mid)
            n = count_at(org, a, b, tri, oi, tri_b, steady)[1]
            if n >= nom:
                lo = mid
            else:
                hi = mid
            if hi - lo < 0.005:
                break
        return lo

    ey = min(edge(0, -1), edge(0, 1))
    ep = min(edge(1, -1), edge(1, 1))
    return dict(yaw_deg=round(ey, 3), pitch_deg=round(ep, 3),
                yaw_px=round(ey * sp.PX_Y, 1), pitch_px=round(ep * sp.PX_P, 1),
                px=round(min(ey * sp.PX_Y, ep * sp.PX_P), 1))


# ---------------------------------------------------------------- D 俯角全域
def audit_pitch(d, arena, props, tri, oi, tri_b, tri_cover, tri_all, steady, slots, view):
    """固定目标世界点，改变相机俯角后重投影 → 再瞄 → 段数。"""
    cpos = np.array(sp.expand(slots[view], "camera_position"), np.float64)
    char = sp.expand(slots[view], "character_position")
    gy = float(char[1]) + sb.GUN_H
    grid = [round(x * 1.0, 1) for x in range(-6, 7)]
    per = []
    for p in d["points"]:
        P = np.array(p["pos"], float)
        row = []
        for po in grid:
            tw, tc, th, asp = vp.cam_basis(FOV, po, 0.0)
            pr = vp.project(P, cpos, tc, th, asp)
            if pr is None or not (0 <= pr[0] < W and 0 <= pr[1] < H):
                row.append(0)
                continue
            dv = vp.pix_dir(float(pr[0]), float(pr[1]), tw, th, asp)
            tt = _ray_t(cpos, dv, tri_all)
            if not math.isfinite(tt):
                row.append(0)
                continue
            Pc = cpos + dv * tt
            tc2 = _ray_t(cpos, dv, tri_cover)
            if math.isfinite(tc2) and tc2 < tt - 0.05:
                row.append(-1)                    # 被自家掩体挡住
                continue
            org = np.array([char[0], gy, char[2]], float)
            w = Pc - org
            y2 = math.degrees(math.atan2(w[0], w[2]))
            p2 = math.degrees(math.atan2(w[1], math.hypot(w[0], w[2])))
            row.append(count_at(org, y2, p2, tri, oi, tri_b, steady)[1])
        nom = p["n_steady"]
        keep = sum(1 for v in row if v >= nom)
        per.append(dict(no=p["no"], nom=nom, row=row, keep=round(keep / len(grid), 3),
                        span=[g for g, v in zip(grid, row) if v >= nom]))
    return dict(grid=grid, per_point=per)


def _ray_t(origin, d, tri):
    """只求最近交点距离。"""
    if not len(tri):
        return math.inf
    v0 = tri[:, 0, :]; e1 = tri[:, 1, :] - v0; e2 = tri[:, 2, :] - v0
    pv = np.cross(d[None, :], e2)
    det = np.einsum("tj,tj->t", e1, pv)
    m = np.abs(det) > 1e-9
    inv = np.where(m, 1.0 / np.where(m, det, 1.0), 0.0)
    tv = origin[None, :] - v0
    u = np.einsum("tj,tj->t", tv, pv) * inv
    qv = np.cross(tv, e1)
    vv = np.einsum("j,tj->t", d, qv) * inv
    t = np.einsum("tj,tj->t", e2, qv) * inv
    ok = m & (u >= -1e-5) & (vv >= -1e-5) & (u + vv <= 1 + 1e-5) & (t > 1e-3)
    if not ok.any():
        return math.inf
    return float(np.min(np.where(ok, t, np.inf)))


# ---------------------------------------------------------------- C 五阵位
def audit_slots(d, slots, orgs, tri, oi, tri_b, steady, blk_objs=None, bi_b=None):
    out = []
    for p in d["points"]:
        P = np.array(p["pos"], float)
        row, blk = {}, {}
        for k, org in orgs.items():
            w = P - org
            y2 = math.degrees(math.atan2(w[0], w[2]))
            p2 = math.degrees(math.atan2(w[1], math.hypot(w[0], w[2])))
            nall, nst = count_at(org, y2, p2, tri, oi, tri_b, steady)
            row[k] = dict(n=nall, nst=nst)
            if nall == 0:
                # 找出挡在路上的东西
                bd, who = _blocker_who(org, y2, p2, tri_b, blk_objs, bi_b)
                if math.isfinite(bd):
                    blk[k] = dict(d=round(bd, 2), name=who)
        vals = [v["nst"] for v in row.values()]
        out.append(dict(no=p["no"], nom=p["n_steady"], slots=row, blocked=blk,
                        min=min(vals), max=max(vals), spread=max(vals) - min(vals),
                        n_ok=sum(1 for v in vals if v >= p["n_steady"]),
                        n_ok2=sum(1 for v in vals if v >= 2),
                        all_ok=bool(min(vals) >= p["n_steady"])))
    return out


def _blocker_who(org, yaw, pitch, tri_b, blk_objs, bi_b):
    if tri_b is None or not len(tri_b):
        return math.inf, None
    dd = sb.ray_dirs(yaw, pitch)[0]
    t = _ray_t_all(org, dd, tri_b)
    if not math.isfinite(t):
        return math.inf, None
    # 再求一次带 owner 的
    if bi_b is None:
        return t, None
    v0 = tri_b[:, 0, :]; e1 = tri_b[:, 1, :] - v0; e2 = tri_b[:, 2, :] - v0
    D = np.broadcast_to(dd, (len(tri_b), 3))
    pv = np.cross(D, e2); det = np.einsum("tj,tj->t", e1, pv)
    m = np.abs(det) > 1e-9
    inv = np.where(m, 1.0 / np.where(m, det, 1.0), 0.0)
    tv = org - v0
    u = np.einsum("tj,tj->t", tv, pv) * inv
    qv = np.cross(tv, e1)
    vv = np.einsum("tj,tj->t", D, qv) * inv
    tt = np.einsum("tj,tj->t", e2, qv) * inv
    ok = m & (u >= -1e-5) & (vv >= -1e-5) & (u + vv <= 1 + 1e-5) & (tt > 1e-3)
    if not ok.any():
        return math.inf, None
    idx = np.where(ok)[0]
    k = idx[np.argmin(tt[idx])]
    nm = blk_objs[bi_b[k]]["name"] if blk_objs else None
    return float(tt[k]), nm


def _ray_t_all(origin, d, tri):
    return _ray_t(origin, d, tri)


# ---------------------------------------------------------------- G 枪口高度
GUN_H_GRID = [1.0, 1.45, 1.9, 2.3, 2.6]


def audit_gunh(d, slots, tri, oi, tri_b, steady):
    """枪口高度扫描：蹲着被掩体挡住时，抬高能不能打出去。

    这一项回答的是「是几何死角，还是姿态问题」：
    如果 1.45m 打不到、2.3m 能打到 → 玩家站起来/侧身就能用，点位仍成立；
    如果 2.6m 也打不到 → 真的是死角，这个阵位彻底没戏。
    """
    out = []
    for p in d["points"]:
        P = np.array(p["pos"], float)
        row = {}
        for k in sorted(slots):
            cp = sp.expand(slots[k], "character_position")
            if not cp:
                continue
            col = []
            for gh in GUN_H_GRID:
                org = np.array([cp[0], cp[1] + gh, cp[2]], np.float64)
                w = P - org
                y2 = math.degrees(math.atan2(w[0], w[2]))
                p2 = math.degrees(math.atan2(w[1], math.hypot(w[0], w[2])))
                col.append(count_at(org, y2, p2, tri, oi, tri_b, steady)[1])
            row[k] = col
        out.append(dict(no=p["no"], nom=p["n_steady"], grid=GUN_H_GRID, slots=row))
    return dict(grid=GUN_H_GRID, per_point=out)


# ---------------------------------------------------------------- E 宽高比
RATIOS = [("16:9", 16 / 9, "手机主流/PC 默认"), ("20:9", 20 / 9, "全面屏手机"),
          ("21:9", 21 / 9, "带鱼屏模拟器"), ("16:10", 16 / 10, "老笔记本"),
          ("4:3", 4 / 3, "平板")]


def audit_aspect(d, mode="vfov"):
    """纵向 FOV 固定（vfov）或横向 FOV 固定（hfov）时，同一点在其他宽高比下的像素。

    返回每点在各宽高比下的像素，以及相对 16:9 的偏移（以 1600×900 为基准坐标系）。
    """
    base_asp = W / H
    res = []
    for p in d["points"]:
        u, v = p["px"]
        th = math.tan(math.radians(FOV / 2))
        x = ((u + 0.5) / W * 2 - 1) * th * base_asp      # NDC
        y = (1 - (v + 0.5) / H * 2) * th
        row = {}
        for name, asp, _ in RATIOS:
            if mode == "vfov":
                th2 = th
                w2 = H * asp
            else:
                th2 = th * base_asp / asp
                w2 = W
            u2 = ((x / (th2 * asp)) * 0.5 + 0.5) * w2
            v2 = (0.5 - (y / th2) * 0.5) * H
            row[name] = [round(u2, 1), round(v2, 1)]
        # 按同一屏幕宽度归一后再比较（把别人屏幕上的坐标换回 1600 宽）
        off = {}
        for name, asp, _ in RATIOS:
            w2 = H * asp if mode == "vfov" else W
            off[name] = round(abs(row[name][0] / w2 * W - u), 1)
        res.append(dict(no=p["no"], px=row, off=off, off_max=max(off.values())))
    return dict(mode=mode, ratios=[dict(n=n, asp=round(a, 3), note=t) for n, a, t in RATIOS],
                per_point=res)


# ---------------------------------------------------------------- F 可辨识度
def audit_size(p, prop_by_name, d_hitname, cam):
    """首击物体投影包围盒（用物体顶点近似）。"""
    name = d_hitname[0]["name"]
    obj = prop_by_name.get(name)
    if obj is None:
        return None
    tw, tc, th, asp = vp.cam_basis(FOV)
    vs = np.array(obj.get("v") or [], float)
    if not len(vs):
        return None
    pr = []
    for P in vs:
        q = vp.project(P, cam, tc, th, asp)
        if q is not None:
            pr.append(q)
    if not pr:
        return None
    pr = np.array(pr)
    bw = float(pr[:, 0].max() - pr[:, 0].min())
    bh = float(pr[:, 1].max() - pr[:, 1].min())
    dist = float(d_hitname[0]["d"])
    # 角尺寸（度）
    ang = 2 * math.degrees(math.atan(max(bw, bh) / 2 / max(1e-3, dist) / sp.PX_Y))
    return dict(name=name, d=round(dist, 1), bbox=[round(bw, 1), round(bh, 1)],
                area_pct=round(bw * bh / (W * H) * 100, 3), ang_deg=round(ang, 2))


# ---------------------------------------------------------------- 主流程
def audit(arena, top=0, view=None):
    path = PATH.px(arena, view or "cover_3")
    d = json.load(open(path, encoding="utf-8"))
    props, objs, tri, oi, tri_b, tri_cover, tri_all, steady = load_arena(arena)
    slots = PATH.slots(arena)
    view = d["view"]
    cam = np.array(sp.expand(slots[view], "camera_position"), np.float64)
    char = sp.expand(slots[view], "character_position")

    orgs = {}
    for k in sorted(slots):
        cp = sp.expand(slots[k], "character_position")
        if cp:
            orgs[k] = np.array([cp[0], cp[1] + sb.GUN_H, cp[2]], np.float64)
    org = orgs[view]

    pts = d["points"][:top] if top else d["points"]
    print("[%s] %d 点（全量 %d）" % (arena, len(pts), len(d["points"])))

    t0 = time.time()
    A = audit_roundtrip(d, cam, char)
    print("  A 往返自洽 err_max=%s px  perp_max=%s m  -> %s"
          % (A["err_max"], A["perp_max"], "OK" if A["ok"] else "!! 不一致"))

    B = {}
    for p in pts:
        B[p["no"]] = audit_cone(p, org, tri, oi, tri_b, steady)
    print("  B 容错锥 %.1fs" % (time.time() - t0))

    C = audit_slots(d, slots, orgs, tri, oi, tri_b, steady, BLK_OBJS[0], BLK_OBJS[1])
    print("  C 五阵位 %.1fs" % (time.time() - t0))

    G = audit_gunh(d, slots, tri, oi, tri_b, steady)
    print("  G 枪口高度 %.1fs" % (time.time() - t0))

    D = audit_pitch(d, arena, props, tri, oi, tri_b, tri_cover, tri_all, steady, slots, view)
    print("  D 俯角全域 %.1fs" % (time.time() - t0))

    E1 = audit_aspect(d, "vfov")
    E2 = audit_aspect(d, "hfov")

    F = {}
    prop_by_name = {p.get("n", ""): p for p in props}
    for p in pts:
        F[p["no"]] = audit_size(p, prop_by_name, p["detail"], cam)
    print("  E/F 完成 %.1fs" % (time.time() - t0))

    # ---- 汇总评级 ----
    # 口径（v12）：
    #   「准不准」在玩家那边拆成两件事 ——
    #   ① 照着红点压，压得住吗？          → 锥宽 cone_px（相机无关）
    #   ② 站我这个位置打得到吗？          → 阵位 n_ok / n_ok2
    #   ③ 相机俯角一变还成立吗？          → pitch_keep（follow 免疫，仅作否决）
    # 三项都过才给 S/A；阵位是**否决项**，因为它是玩家最容易踩的坑。
    Bmap = B
    Cmap = {c["no"]: c for c in C}
    Dmap = {x["no"]: x for x in D["per_point"]}
    Gmap = {x["no"]: x for x in G["per_point"]}
    Emap = {x["no"]: x for x in E1["per_point"]}
    rows = []
    for p in pts:
        no = p["no"]
        b = Bmap.get(no) or {}
        c = Cmap.get(no) or {}
        dd = Dmap.get(no) or {}
        f = F.get(no) or {}
        g = Gmap.get(no) or {}
        eoff = (Emap.get(no) or {}).get("off_max") or 0
        cone = b.get("px", 0)
        min_slot = c.get("min", 0)
        n_ok = c.get("n_ok", 0)
        n_ok2 = c.get("n_ok2", 0)
        nom = p["n_steady"]
        # 抬高枪口后能不能救回来
        rescue = {}
        for k, col in (g.get("slots") or {}).items():
            first = col[0] if col else 0
            best = max(col) if col else 0
            rescue[k] = dict(base=first, best=best,
                             need=GUN_H_GRID[col.index(best)] if col and best > first else None)
        fatal, warn = [], []
        if cone < 2.0:
            fatal.append("锥宽%.1fpx" % cone)
        if dd.get("keep", 1) < 0.6:
            fatal.append("俯角敏感")
        if f.get("bbox") and max(f["bbox"]) < 8:
            fatal.append("首击物仅%dpx" % max(f["bbox"]))
        if n_ok2 <= 1:
            fatal.append("仅%d个阵位能用" % n_ok2)
        elif n_ok2 <= 2:
            warn.append("仅%d/5阵位" % n_ok2)
        if c.get("blocked"):
            warn.append("挡:%s" % ",".join(sorted(c["blocked"])))
        if eoff >= 100:
            warn.append("宽屏漂%.0fpx" % eoff)
        if fatal:
            grade = "D"
        elif cone >= 8 and dd.get("keep", 1) >= 0.9 and n_ok >= 5:
            grade = "S"
        elif cone >= 5 and dd.get("keep", 1) >= 0.85 and n_ok >= 4:
            grade = "A"
        elif cone >= 3.5 and n_ok2 >= 3:
            grade = "B"
        elif cone >= 2.5:
            grade = "C"
        else:
            grade = "D"
        rows.append(dict(no=no, nom=nom, px=p["px"], cone_px=cone,
                         cone_yaw=b.get("yaw_deg"), cone_pitch=b.get("pitch_deg"),
                         cone_yaw_px=b.get("yaw_px"), cone_pitch_px=b.get("pitch_px"),
                         rad=p.get("rad"), slot_min=min_slot, slot_n=len(c.get("slots") or {}),
                         n_ok=n_ok, n_ok2=n_ok2, slot_spread=c.get("spread"),
                         blocked=c.get("blocked"), rescue=rescue, drift=eoff,
                         pitch_keep=dd.get("keep"), pitch_span=dd.get("span"),
                         first=p["detail"][0]["name"], first_d=p["detail"][0]["d"],
                         obj=f, grade=grade, fatal=fatal, warn=warn))

    print("  评级: " + "  ".join("%s×%d" % (g, sum(1 for r in rows if r["grade"] == g))
                                for g in ("S", "A", "B", "C", "D")))
    out = dict(arena=arena, view=view, ver="v12-audit",
               n_points=len(d["points"]), n_audited=len(pts),
               A=A, B={str(k): v for k, v in B.items()}, C=C, D=D, G=G,
               E_vfov=E1, E_hfov=E2, F={str(k): v for k, v in F.items()},
               gunh_grid=GUN_H_GRID,
               rows=rows, secs=round(time.time() - t0, 1))
    json.dump(out, open(PATH.audit(arena, view or "cover_3"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    top = 0
    view = None
    for a in sys.argv[1:]:
        if a.startswith("--top="):
            top = int(a.split("=")[1])
        if a.startswith("--view="):
            view = a.split("=")[1]
    arg = args[0] if args else "all"
    arenas = (["001", "002", "003", "004", "005"] if arg == "all"
              else ["mw001", "mw002", "mw003"] if arg == "mw" else [arg])
    allrows = []
    for a in arenas:
        o = audit(a, top=top, view=view)
        allrows += [dict(r, arena=a) for r in o["rows"]]
    if len(arenas) > 1:
        print("\n==== 汇总 ====")
        print("%-6s %-3s %-3s %-8s %-6s %-6s %-5s %-5s %s"
              % ("arena", "no", "nom", "cone_px", "slotmin", "pitch", "obj", "grade", "原因"))
        for r in allrows:
            print("%-6s %-3d %-3d %-8s %-6s %-6s %-5s %-5s %s"
                  % (r["arena"], r["no"], r["nom"], r["cone_px"], r["slot_min"],
                     r["pitch_keep"], (r["obj"] or {}).get("bbox"), r["grade"],
                     ",".join(r["fatal"]) or "-"))
        json.dump(allrows, open(PATH.ana_shared("audit_all.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
