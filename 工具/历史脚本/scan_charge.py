# -*- coding: utf-8 -*-
"""按游戏内配置做「穿透充能射线」扫描。

配置来源（全部拆包）：
  5 个阵位       cover_1..cover_5 的世界变换（slots.json）
                 每个阵位下挂 character_position / camera_position
  相机           Camera.field of view = 60, near 0.1, far 300
  hitbox 分类    场景节点 root：soft / medium / hard / cover_object
                 对应 ConfigBattleTable：soft_object_hp=100, medium=500, hard=1000, cover=8000
  爆裂条          burst_energy_max = 1000000（内部值）；显示口径 = /100 = 10000
  每发命中基础     ulti_gauge_shot_hit = 4（内部单位）
  蓄力起点        SpotSetting.AimStartPosition1..5

充能口径说明（重要，避免混用）：
  社区/百科的「攻击充能 2.80%」= 每发命中的爆裂条百分比。
  换算到显示口径：0.028 * 10000 = 280 能量/发。
  换算到内部口径：0.028 * 1000000 = 28000。
  两者只差 100 倍，百分比与发数结论完全一致。本脚本同时输出两套。

穿透模型：
  子弹从角色枪口出发，沿瞄准方向贯穿；命中 N 个不同 hitbox 即 N 倍能量。
  一枪命中数 N 只由几何决定 —— 这正是「没有明显特征的判定点」的来源。

用法：
  python scan_charge.py 001          -> 导出/charge_001.json
  python scan_charge.py all
"""
import json, math, os, sys
import numpy as np

W, H = 10000.0, 100.0          # 显示口径 / 内部口径除数
PER_SHOT_PCT = 2.80            # 小红帽 SR 攻击充能（%）
CHARGE_PER_SHOT = PER_SHOT_PCT / 100.0 * W      # 显示口径 280
BAR = W                                          # 10000
GUN_H = 1.45                   # 枪口相对角色脚底的高度（m，表现参数）

HITBOX = {"soft": 100, "medium": 500, "hard": 1000}
# cover_object 是队伍掩体（barrier / forklift），子弹不会打自己掩体，不计入
COVER = "cover_object"
MAX_SPAN = 60.0      # 单件 bbox 最大边长超过此值视为远景背景，不计入充能
MIN_DIST = 2.0       # 距枪口过近的命中视为自身周围杂物


def load_tris(props):
    tris, owner = [], []      # tris: (T,3,3) 三点；owner: (T,) 物体序号
    objs = []                 # meta
    skipped = {"cover": 0, "huge": 0}
    for p in props:
        g = p.get("g")
        if g == COVER:
            skipped["cover"] += 1
            continue
        if g not in HITBOX:
            continue
        v = p.get("v") or []
        idx = p.get("i") or []
        if len(v) < 3 or len(idx) < 3:
            continue
        xs = [c[0] for c in v]; ys = [c[1] for c in v]; zs = [c[2] for c in v]
        span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
        if span > MAX_SPAN:
            skipped["huge"] += 1
            continue
        oi = len(objs)
        objs.append(dict(name=p.get("n", ""), grp=g, hp=HITBOX[g], span=round(span, 1),
                         center=[round(sum(xs) / len(v), 1), round(sum(ys) / len(v), 1),
                                 round(sum(zs) / len(v), 1)]))
        for t in range(0, len(idx) - 2, 3):
            a, b, c = idx[t], idx[t + 1], idx[t + 2]
            if a < len(v) and b < len(v) and c < len(v):
                tris.append([v[a], v[b], v[c]])
                owner.append(oi)
    return objs, tris, owner, skipped


def ray_hits(origin, dirs, tri, eps=1e-6):
    """numpy 向量化 Möller-Trumbore。
    origin (3,)  dirs (M,3)  tri (T,3,3)  ->  (M,T) 命中距离，未命中为 inf"""
    v0 = tri[:, 0, :]                        # (T,3)
    e1 = tri[:, 1, :] - v0                   # (T,3)
    e2 = tri[:, 2, :] - v0                   # (T,3)
    M, T = len(dirs), len(tri)

    pv = np.cross(dirs[:, None, :], e2[None, :, :])            # (M,T,3)
    det = np.einsum("tj,mtj->mt", e1, pv)                      # (M,T)
    ok = np.abs(det) > 1e-9
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)

    tv = np.broadcast_to(origin[None, None, :], (M, T, 3)) - v0[None, :, :]
    u = np.einsum("mtj,mtj->mt", tv, pv) * inv
    qv = np.cross(tv, e1[None, :, :])                          # (M,T,3)
    vv = np.einsum("mj,mtj->mt", dirs, qv) * inv
    t = np.einsum("tj,mtj->mt", e2, qv) * inv

    hit = ok & (u >= -1e-5) & (vv >= -1e-5) & (u + vv <= 1 + 1e-5) & (t > eps)
    return np.where(hit, t, np.inf)


def scan(arena, slot_keys, coarse_yaw=1.0, coarse_pitch=1.0,
         yaw_range=(-42.0, 42.0), pitch_range=(-3.0, 13.0), keep=6):
    asm = json.load(open(os.path.join("导出", "assembly_%s.json" % arena), encoding="utf-8"))
    slots = json.load(open(os.path.join("导出", "slots.json"), encoding="utf-8"))[arena]

    objs, tr, oi, skipped = load_tris(asm["props"])
    tri = np.array(tr, dtype=np.float64)      # (T,3,3)
    oi = np.array(oi, dtype=np.int32)
    print("  hitbox obj=%d tri=%d (跳过 cover=%d 远景=%d)" % (
        len(objs), len(tri), skipped["cover"], skipped["huge"]))

    results = {}
    for sk in slot_keys:
        e = slots[sk]
        P = e["character_position"][0] if isinstance(e.get("character_position"), list) else None
        if P is None:
            continue
        origin = np.array([P[0], P[1] + GUN_H, P[2]], dtype=np.float64)
        cam = e["cam"]

        yaws = np.arange(yaw_range[0], yaw_range[1] + 1e-6, coarse_yaw)
        pits = np.arange(pitch_range[0], pitch_range[1] + 1e-6, coarse_pitch)
        cand = []
        for pitch in pits:
            cp = math.cos(math.radians(pitch))
            sp = math.sin(math.radians(pitch))
            dirs = np.array([[math.sin(math.radians(y)) * cp, sp, math.cos(math.radians(y)) * cp]
                             for y in yaws])
            tt = ray_hits(origin, dirs, tri)          # (M, T)
            for i, y in enumerate(yaws):
                ti = tt[i]
                ti = np.where(ti >= MIN_DIST, ti, np.inf)   # 排除贴脸杂物
                m = np.isfinite(ti)
                if not m.any():
                    continue
                hit_objs = np.unique(oi[m])
                dists = ti[m]
                cand.append(dict(yaw=round(float(y), 1), pitch=round(float(pitch), 1),
                                 n=int(len(hit_objs)),
                                 first=round(float(dists.min()), 1),
                                 last=round(float(dists.max()), 1),
                                 objs=[int(x) for x in hit_objs]))

        # 同一命中组合只保留一次（取最靠中间的角度）
        best = {}
        for c in cand:
            key = tuple(sorted(c["objs"]))
            cur = best.get(key)
            if cur is None or abs(c["yaw"]) < abs(cur["yaw"]):
                best[key] = c

        # 排序后做角度分散：pick 之间最小角距 5°，避免标注堆在一起
        pool = sorted(best.values(), key=lambda c: (-c["n"], c["first"]))
        picked = []
        for c in pool:
            if any(abs(c["yaw"] - p["yaw"]) < 5 and abs(c["pitch"] - p["pitch"]) < 2.5
                   for p in picked):
                continue
            picked.append(c)
            if len(picked) >= keep:
                break
        ranked = picked

        for c in ranked:
            c["energy"] = c["n"] * CHARGE_PER_SHOT
            c["shots"] = int(math.ceil(BAR / c["energy"])) if c["energy"] else None
            c["pct"] = round(c["n"] * PER_SHOT_PCT, 2)
            c["detail"] = [dict(name=objs[i]["name"], grp=objs[i]["grp"], hp=objs[i]["hp"])
                           for i in c["objs"]]

        results[sk] = dict(
            char=[round(v, 3) for v in P],
            cam=[round(v, 3) for v in cam] if cam else None,
            origin=[round(float(v), 3) for v in origin],
            top=ranked, total_cand=len(cand))

    return dict(arena="sbg_swamplandjungle_%s" % arena,
                fov=60.0, near=0.1, far=300.0,
                charge_per_shot=CHARGE_PER_SHOT, bar=BAR,
                per_shot_base=4, slots=results)


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "001"
    keys = ["cover_1", "cover_2", "cover_3", "cover_4", "cover_5"]
    arenas = ["001", "002", "003", "004", "005"] if arg == "all" else [arg]
    for a in arenas:
        print("== arena", a)
        d = scan(a, keys)
        out = os.path.join("导出", "charge_%s.json" % a)
        json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False)
        for sk, r in d["slots"].items():
            t = r["top"][0] if r["top"] else None
            if t:
                print("   %s  char=%s  best: n=%d  yaw=%+.1f pitch=%+.1f  %.1f%%  %d发  first=%.1fm" % (
                    sk, r["char"], t["n"], t["yaw"], t["pitch"], t["pct"], t["shots"], t["first"]))
        print("   ->", out)


if __name__ == "__main__":
    main()
