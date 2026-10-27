# -*- coding: utf-8 -*-
"""H36-35 充能点位扫描：真实战场几何 + 敌人地面点位。

输出 scan_result.json：每张战场 Top5 点位（含命中明细）
"""
import json, math, collections, os

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = 280.0
GAUGE = 10000.0
TPS = 1.0 + 0.2 + 2.0 / 6.0          # 蓄力 1.0s + 后摇 0.2s + 换弹摊销 0.333s
DEST = {"soft", "medium", "hard", "dynamic_object"}
GRADE_CN = {"soft": "软", "medium": "中", "hard": "硬", "dynamic_object": "动态"}

PLAYER_Z = 4.5
PX_MIN, PX_MAX, PX_STEP = -7.5, 8.0, 0.25
YAW_MIN, YAW_MAX, YAW_STEP = -60.0, 60.0, 0.5
Z_MAX = 72.0
LANE = 0.55          # 敌点位命中半径（米）
STATIC_BLOCK = False  # 静态布景是否挡弹

def seg_rect(ox, oz, dx, dz, b):
    x0, x1, z0, z1 = b[0], b[3], b[2], b[5]
    tmin, tmax = 0.0, 1e9
    if abs(dx) < 1e-9:
        if ox < x0 or ox > x1:
            return None
    else:
        t1, t2 = (x0 - ox) / dx, (x1 - ox) / dx
        if t1 > t2:
            t1, t2 = t2, t1
        tmin = max(tmin, t1); tmax = min(tmax, t2)
    if abs(dz) < 1e-9:
        if oz < z0 or oz > z1:
            return None
    else:
        t1, t2 = (z0 - oz) / dz, (z1 - oz) / dz
        if t1 > t2:
            t1, t2 = t2, t1
        tmin = max(tmin, t1); tmax = min(tmax, t2)
    if tmax < tmin or tmax < 0:
        return None
    return max(tmin, 0.0)

def load_arena(idx):
    d = json.load(open(os.path.join(ROOT, "..", "数据", "导出", "map_%s.json" % idx), encoding="utf-8"))
    props = []
    for p in d["props"]:
        b = p["b"]
        if not b or b[5] <= 0.5 or b[2] > Z_MAX:
            continue
        props.append(p)
    gp = json.load(open(os.path.join(ROOT, "ground_points.json"), encoding="utf-8"))
    g = gp["point_grd_swamplandjungle_" + idx]["GroundPoints"]
    pts = [(float(k), v["x"], v["z"]) for k, v in g.items() if k != "0"]
    return d, props, pts

def shoot(px, yaw, props, pts):
    r = math.radians(yaw)
    dx, dz = math.sin(r), math.cos(r)
    hits = []
    for p in props:
        if p["g"] not in DEST:
            if not STATIC_BLOCK:
                continue
        t = seg_rect(px, PLAYER_Z, dx, dz, p["b"])
        if t is not None:
            hits.append((t, p))
    hits.sort(key=lambda x: x[0])
    # 敌方点位：投影距离 + 横向偏差
    ph = []
    for pid, x, z in pts:
        if z <= PLAYER_Z:
            continue
        along = (x - px) * dx + (z - PLAYER_Z) * dz
        if along <= 0:
            continue
        lat = abs((x - px) * dz - (z - PLAYER_Z) * dx)
        if lat <= LANE:
            ph.append((along, pid, round(lat, 2)))
    ph.sort()
    return hits, ph

def scan(idx):
    d, props, pts = load_arena(idx)
    dest_props = [p for p in props if p["g"] in DEST]
    res = []
    a = PX_MIN
    while a <= PX_MAX + 1e-9:
        t = YAW_MIN
        while t <= YAW_MAX + 1e-9:
            h, ph = shoot(a, t, dest_props, pts)
            res.append({"px": round(a, 2), "yaw": round(t, 1),
                        "hits": h, "pts": ph})
            t += YAW_STEP
        a += PX_STEP
    # 排序：地形段数优先，再敌点数
    res.sort(key=lambda r: (-len(r["hits"]), -len(r["pts"]), abs(r["px"])))
    keep = []
    for r in res:
        if len(r["hits"]) + len(r["pts"]) < 2:
            continue
        if all(abs(k["px"] - r["px"]) > 2.0 or abs(k["yaw"] - r["yaw"]) > 4 for k in keep):
            keep.append(r)
        if len(keep) >= 5:
            break
    out = []
    for r in keep:
        n = len(r["hits"]); m = len(r["pts"])
        e0 = n * BASE; e1 = (n + m) * BASE
        gs = collections.Counter(GRADE_CN.get(p["g"], p["g"]) for _, p in r["hits"])
        out.append({
            "px": r["px"], "yaw": r["yaw"],
            "nHit": n, "nPt": m,
            "e0": e0, "e1": e1,
            "shots0": math.ceil(GAUGE / e0) if e0 else None,
            "shots1": math.ceil(GAUGE / e1) if e1 else None,
            "grade": dict(gs),
            "hitList": [{"n": p["n"].replace("sbg_swamplandjungle_", ""), "g": p["g"],
                         "t": round(t, 1)} for t, p in r["hits"]][:14],
            "ptList": [{"id": pid, "t": round(t, 1)} for t, pid, _ in r["pts"]][:14],
        })
    return {"arena": d["arena"], "anchors": d["anchors"], "props": props,
            "points": [{"id": pid, "x": round(x, 2), "z": round(z, 2)} for pid, x, z in pts],
            "top": out, "nDest": len(dest_props)}

if __name__ == "__main__":
    allout = {}
    for idx in ["001", "002", "003", "004", "005"]:
        r = scan(idx)
        allout[idx] = r
        print("=" * 60)
        print("战场 %s  可破坏 %d  敌点位 %d" % (r["arena"], r["nDest"], len(r["points"])))
        for i, s in enumerate(r["top"], 1):
            print("  %d. x=%+.2f yaw=%+5.1f  地形%d段+敌点%d个  保底%4d(%.1f%%)  理想%4d(%.1f%%)  满%s/%s发"
                  % (i, s["px"], s["yaw"], s["nHit"], s["nPt"], s["e0"], s["e0"] / 100,
                     s["e1"], s["e1"] / 100, s["shots0"], s["shots1"]))
            print("      地形 %s | 敌点 %s" % (s["grade"], [p["id"] for p in s["ptList"]][:8]))
    json.dump(allout, open(os.path.join(ROOT, "scan_result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    print("\nsaved scan_result.json", os.path.getsize(os.path.join(ROOT, "scan_result.json")))
