# -*- coding: utf-8 -*-
"""点位可信度：蒙特卡洛扰动复核（v10.5）

为什么要这一层
--------------
`scan_px.py` 给的是**一组假设下的确定解**：相机在 `camera_position`、朝向沿 +z 且
rotation=identity（俯角 0）、角色站在 `character_position` 正中、枪口高 1.45m、
准星能精确压到某一颗像素。这些里有一半是**推断**。所以「4 段」这个数字可不可靠，
取决于这些假设被抖动时它还站不站得住。本脚本不找新点，只回答一个问题：
**同一颗目标，抖一遍再打，还剩几段。**

两种「抖法」，对应两种真实用法
------------------------------
玩家的实际动作是「看图里那个点 → 把准星对到那个物体上」。所以：

  · **跟随模式（主指标）**：目标的世界坐标固定，相机/角色参数被扰动后，
    把目标重新投影回屏幕（模拟玩家在新画面里重新找到它），再叠手抖 → 反推枪口角 → 段数。
    它衡量的是「这个点本身好不好打」。
  · **死记模式（对照）**：像素坐标固定不动，相机参数一扰动，同一个像素就瞄到别处。
    它衡量的是「我们图上标的那个像素，换个相机还准不准」。

两者之差就是**标注风险**：跟随模式高、死记模式低，说明这个点对相机的标定很敏感
（图上的红点位置不可靠），需要先校准相机再谈点位。

扰动因子：哪些进蒙特卡洛，哪些只做敏感性
----------------------------------------
随机误差（进蒙特卡洛，影响可信度）：
| 因子     | 1σ      | 现实含义                                    |
|----------|---------|---------------------------------------------|
| char_pos | 0.30 m  | 掩体后左右走位，站位不会正好在阵位中心      |
| gun_h    | 0.15 m  | 不同角色模型的枪口高度差                    |
| aim_px   | max(2, 0.8R) px | 准星手抖（R = 支撑半径，越窄的点要求越精） |
| recoil   | 0.12°   | 连射时枪口上跳（纵向）                      |
| geo      | 1.5 px  | 渲染网格 vs 碰撞体的几何简化误差            |

系统性偏差（不进蒙特卡洛，只做敏感性 —— 它们会让**整张图**一起偏，不是单点问题）：
`cam_pitch`（俯角 0 的假设）、`cam_yaw`、`fov`。这三项错了，图上所有点一起偏，
玩家第一眼就会发现画面与实机对不上，属于「工具级失效」，所以单独报「漂移像素」，
不摊到单点可信度里 —— 但也给出警戒线：漂移 > 40px 时整张图的标注就该重做。

可信度 = 100 × (0.60·达标率 + 0.25·可用率 + 0.15·P10 相对标称)
  达标率 P(稳态 ≥ 标称)  —— 「说 4 段就真给 4 段」的概率
  可用率 P(稳态 ≥ 2)     —— 不至于退化成单判的概率
  P10 相对标称           —— 最差 10% 还剩几成（保守下界）

用法
----
  python verify_px.py mw003              # 单图，300 次
  python verify_px.py all --sim=500
  python verify_px.py mw002 --sim=800    # 想更稳就加样本
"""
import json, math, os, sys, time

import numpy as np

import scan_best as sb
import scan_px as sp

# ---------------------------------------------------------------- 扰动模型
STOCH = {                                        # 进蒙特卡洛
    "char_pos": (0.30, 0.75, "m", "掩体后走位，站位不在阵位中心"),
    "gun_h":    (0.15, 0.40, "m", "角色模型枪口高度差"),
    "aim_px":   (2.00, None, "px", "准星手抖（σ 随支撑半径放大：max(2, 0.8R)）"),
    "recoil":   (0.12, 0.35, "deg", "连射枪口上跳（纵向）"),
}
SYST = {                                          # 只做敏感性，不进评分
    "cam_pitch": (2.0, 5.0, "deg", "相机俯角（rotation=identity 的假设，风险最高）"),
    "cam_yaw":   (0.8, 2.0, "deg", "机位朝向偏转"),
    "fov":       (0.8, 2.0, "deg", "视场角 60 的假设"),
    "cam_pos":   (0.10, 0.25, "m", "camera_position 误差（三轴）"),
}
GEO_PX = 1.5                                     # 几何简化误差（等效像素）

W_HIT, W_KEEP, W_LOW = 0.60, 0.25, 0.15
GRADE = [(80.0, "A"), (68.0, "B"), (52.0, "C"), (-1.0, "D")]
GRADE_TXT = {
    "A": "多轮扰动仍稳定达标，可照打",
    "B": "基本稳，个别条件掉 1 段",
    "C": "条件性可用，站位/节奏要固定",
    "D": "不建议依赖，只作备选",
}
DRIFT_WARN = 40.0                                # 标注漂移警戒线（px）


# ---------------------------------------------------------------- 几何
def ray_first(origin, d, tri, oi, min_dist=1e-3):
    if not len(tri):
        return math.inf, -1
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
    ok = m & (u >= -1e-5) & (vv >= -1e-5) & (u + vv <= 1 + 1e-5) & (t > min_dist)
    if not ok.any():
        return math.inf, -1
    k = int(np.argmin(np.where(ok, t, np.inf)))
    return float(t[k]), int(oi[k])


def cam_basis(fov, pitch_off=0.0, yaw_off=0.0):
    """相机系 ↔ 世界系（相机沿 +z；pitch_off>0 表示向下俯）。返回 (to_world, to_cam, th, asp)。"""
    th = math.tan(math.radians(fov / 2))
    asp = sp.W / sp.H
    cp, spt = math.cos(math.radians(pitch_off)), math.sin(math.radians(pitch_off))
    cy, sy = math.cos(math.radians(yaw_off)), math.sin(math.radians(yaw_off))

    def to_world(d):
        dy = d[1] * cp - d[2] * spt
        dz = d[1] * spt + d[2] * cp
        return np.array([d[0] * cy + dz * sy, dy, -d[0] * sy + dz * cy])

    def to_cam(v):
        x2 = v[0] * cy - v[2] * sy
        z2 = v[0] * sy + v[2] * cy
        return np.array([x2, v[1] * cp + z2 * spt, -v[1] * spt + z2 * cp])

    return to_world, to_cam, th, asp


def pix_dir(u, v, to_world, th, asp):
    x = ((u + 0.5) / sp.W * 2 - 1) * th * asp
    y = (1 - (v + 0.5) / sp.H * 2) * th
    d = np.array([x, y, 1.0])
    d /= np.linalg.norm(d)
    return to_world(d)


def project(P, cam, to_cam, th, asp):
    """世界点 → 像素。点在相机背后返回 None。"""
    v = to_cam(np.asarray(P, float) - cam)
    if v[2] <= 0.05:
        return None
    return np.array([((v[0] / (v[2] * th * asp)) * .5 + .5) * sp.W,
                     (.5 - (v[1] / (v[2] * th)) * .5) * sp.H])


# ---------------------------------------------------------------- 单次模拟
def trial(pt, S, rng, mode, tri, oi, tri_b, tri_cover, tri_all, steady):
    """返回 (稳态段数, 总段数, 原因)。mode='follow' 跟随目标 / 'pixel' 死记像素。"""
    # --- 采样随机误差 ---
    sig_aim = S["aim_sigma"]
    sd_x = rng.normal(0, sig_aim); sd_y = rng.normal(0, sig_aim)
    sd_y += abs(rng.normal(0, STOCH["recoil"][0])) * sp.PX_P   # 0.12° ≈ 1.8px（角度→像素）
    dch = np.clip(rng.normal(0, STOCH["char_pos"][0], 2), -0.75, 0.75)
    gh = float(np.clip(rng.normal(1.45, STOCH["gun_h"][0]), 1.05, 1.85))
    gx = rng.normal(0, GEO_PX); gy = rng.normal(0, GEO_PX)

    # --- 采样系统偏差 ---
    pit_off = float(np.clip(rng.normal(0, SYST["cam_pitch"][0]), -5, 5))
    yaw_off = float(np.clip(rng.normal(0, SYST["cam_yaw"][0]), -2, 2))
    fov = float(np.clip(rng.normal(60, SYST["fov"][0]), 58, 62))
    cpos = S["cam"] + np.clip(rng.normal(0, SYST["cam_pos"][0], 3), -0.25, 0.25)

    to_world, to_cam, th, asp = cam_basis(fov, pit_off, yaw_off)
    if mode == "pixel":
        u, v = pt["px"][0], pt["px"][1]
    else:
        pr = project(pt["_P"], cpos, to_cam, th, asp)
        if pr is None:
            return 0, 0, "off"
        u, v = float(pr[0]), float(pr[1])
        if not (0 <= u < sp.W and 0 <= v < sp.H):
            return 0, 0, "off"
    u += sd_x + gx; v += sd_y + gy

    d = pix_dir(u, v, to_world, th, asp)
    t, _ = ray_first(cpos, d, tri_all, S["oi_all"])
    if not math.isfinite(t):
        return 0, 0, "sky"
    Pc = cpos + d * t
    tc, _ = ray_first(cpos, d, tri_cover, S["oi_cover"])
    if math.isfinite(tc) and tc < t - 0.05:
        return 0, 0, "cover"

    org = np.array([S["char"][0] + dch[0], S["char_y"] + gh, S["char"][2] + dch[1]])
    w = Pc - org
    yaw = math.degrees(math.atan2(w[0], w[2]))
    pit = math.degrees(math.atan2(w[1], math.hypot(w[0], w[2])))
    hits = sb.exact_hits(org, yaw, pit, tri, oi, None)
    if not hits:
        return 0, 0, "miss"
    bd = sp.blocker_dist(org, yaw, pit, tri_b)
    if math.isfinite(bd):
        hits = [(o, dd) for o, dd in hits if dd < bd]
    return sum(1 for o, _ in hits if steady[o]), len(hits), "ok"


def run(pt, S, tri, oi, tri_b, tri_cover, tri_all, steady, N, seed):
    out = {}
    for mode in ("follow", "pixel"):
        rng = np.random.default_rng(seed + (0 if mode == "follow" else 77777))
        st, nn = [], []
        why = {"sky": 0, "cover": 0, "miss": 0, "off": 0}
        for _ in range(N):
            a, b, r = trial(pt, S, rng, mode, tri, oi, tri_b, tri_cover, tri_all, steady)
            st.append(a); nn.append(b)
            if r != "ok":
                why[r] += 1
        st = np.array(st); nn = np.array(nn)
        nom = pt["n_steady"]
        hit = float((st >= nom).mean())
        keep = float((st >= 2).mean())
        p10 = float(np.percentile(st, 10))
        out[mode] = dict(
            p10=round(p10, 2), p50=round(float(np.percentile(st, 50)), 2),
            p90=round(float(np.percentile(st, 90)), 2),
            mean=round(float(st.mean()), 2),
            hit_rate=round(hit, 3), keep_rate=round(keep, 3),
            fail_rate=round(float((st < 2).mean()), 3),
            p_ge={str(k): round(float((st >= k).mean()), 3) for k in (1, 2, 3, 4, 5, 6)},
            why=why,
            _score=W_HIT * hit + W_KEEP * keep + W_LOW * min(1.0, p10 / max(1, nom)),
        )
    f = out["follow"]
    out["follow"]["conf"] = round(100 * f["_score"], 1)
    out["follow"]["grade"] = next(g for th, g in GRADE if out["follow"]["conf"] >= th)
    out["label_risk"] = round(max(0.0, 100 * (f["_score"] - out["pixel"]["_score"])), 1)
    del out["follow"]["_score"], out["pixel"]["_score"]
    return out


def sens(pt, S, tri, oi, tri_b, tri_cover, tri_all, steady):
    """系统偏差敏感性：单因子 ±1σ 时的「漂移像素」与「稳态段数」。"""
    bw, bc, th0, asp0 = cam_basis(60.0)
    base_px = project(pt["_P"], S["cam"], bc, th0, asp0)
    out = {}
    for key, (sig, clip, unit, _) in SYST.items():
        row = []
        for sgn in (-1, 1):
            pit = yaw = 0.0
            fov = 60.0
            cpos = S["cam"].copy()
            val = float(np.clip(sgn * sig, -clip, clip))
            if key == "cam_pitch":
                pit = val
            elif key == "cam_yaw":
                yaw = val
            elif key == "fov":
                fov = 60.0 + val
            elif key == "cam_pos":
                cpos = S["cam"] + np.array([val, val, val]) / math.sqrt(3)
            tw, tc, th, asp = cam_basis(fov, pit, yaw)
            pr = project(pt["_P"], cpos, tc, th, asp)
            drift = float("nan") if (pr is None or base_px is None) else float(np.linalg.norm(pr - base_px))
            # 枪口照新画面打该目标 → 段数
            if pr is None:
                row.append(dict(v=round(val, 2), drift=None, nst=0)); continue
            d = pix_dir(float(pr[0]), float(pr[1]), tw, th, asp)
            t, _ = ray_first(cpos, d, tri_all, S["oi_all"])
            if not math.isfinite(t):
                row.append(dict(v=round(val, 2), drift=round(drift, 1), nst=0)); continue
            Pc = cpos + d * t
            org = np.array([S["char"][0], S["char_y"] + 1.45, S["char"][2]])
            w = Pc - org
            yaw2 = math.degrees(math.atan2(w[0], w[2]))
            pit2 = math.degrees(math.atan2(w[1], math.hypot(w[0], w[2])))
            hits = sb.exact_hits(org, yaw2, pit2, tri, oi, None)
            bd = sp.blocker_dist(org, yaw2, pit2, tri_b)
            if math.isfinite(bd):
                hits = [(o, dd) for o, dd in hits if dd < bd]
            row.append(dict(v=round(val, 2), drift=round(drift, 1),
                            nst=sum(1 for o, _ in hits if steady[o])))
        out[key] = row
    return out


# ---------------------------------------------------------------- 主流程
def verify(arena, N=300, seed=20261023, resort=True):
    path = os.path.join("导出", "px_%s.json" % arena)
    d = json.load(open(path, encoding="utf-8"))
    asm = json.load(open(os.path.join("导出", "assembly_%s.json" % arena), encoding="utf-8"))
    slots = json.load(open(os.path.join("导出", "slots.json"), encoding="utf-8"))[arena]
    props = asm["props"]
    view = d["view"]

    objs, tri, oi, _ = sp.load_props([p for p in props if p.get("g") in sb.HITBOX], set(sb.HITBOX))
    _, tri_b, _, _ = sp.load_props(
        [p for p in props if p.get("g") in sp.BLOCK_GROUPS or p.get("g") == "cover_object"],
        set(sp.BLOCK_GROUPS) | {"cover_object"})
    _, tri_cover, oi_c, _ = sp.load_props(
        [p for p in props if p.get("g") == "cover_object"], {"cover_object"})
    _, tri_all, oi_a, _ = sp.load_props(
        [p for p in props if p.get("g") in sp.SOLID_GROUPS and p.get("g") != "cover_object"],
        set(sp.SOLID_GROUPS) - {"cover_object"})
    steady = [o["grp"] in ("medium", "hard") for o in objs]

    cpos = np.array(sp.expand(slots[view], "camera_position"), np.float64)
    char = sp.expand(slots[view], "character_position")
    S = dict(cam=cpos, char=np.array([char[0], 0.0, char[2]], np.float64),
             char_y=float(char[1]), oi_all=oi_a, oi_cover=oi_c)

    t0 = time.time()
    for p in d["points"]:
        p["_P"] = np.array(p["pos"], np.float64)
        S["aim_sigma"] = max(2.0, 0.8 * float(p.get("rad") or 1))
        v = run(p, S, tri, oi, tri_b, tri_cover, tri_all, steady, N, seed + int(p["no"]) * 1000)
        p["sim"] = v
        p["conf"] = v["follow"]["conf"]
        p["grade"] = v["follow"]["grade"]
        p["label_risk"] = v["label_risk"]
        p["sens"] = sens(p, S, tri, oi, tri_b, tri_cover, tri_all, steady)
        p.pop("_P", None)
    dt = time.time() - t0

    if resort:
        d["points"].sort(key=lambda p: (-p["n_steady"], -round(p["sim"]["follow"]["mean"], 1),
                                        -p["conf"]))
        for i, p in enumerate(d["points"], 1):
            p["no"] = i

    d["ver"] = "v10.5"
    d["verify"] = dict(
        n_sim=N, seed=seed, modes=["follow（主）", "pixel（对照）"],
        stoch={k: dict(sigma=v[0], clip=v[1], unit=v[2], note=v[3]) for k, v in STOCH.items()},
        syst={k: dict(sigma=v[0], clip=v[1], unit=v[2], note=v[3]) for k, v in SYST.items()},
        geo_px=GEO_PX, weights=dict(hit=W_HIT, keep=W_KEEP, low=W_LOW),
        grade_rule={g: t for t, g in GRADE if g != "D"} | {"D": 0},
        grade_text=GRADE_TXT, drift_warn=DRIFT_WARN,
        summary={g: sum(1 for p in d["points"] if p["grade"] == g) for _, g in GRADE},
        secs=round(dt, 1),
    )
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return d


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    N = 300
    for a in sys.argv[1:]:
        if a.startswith("--sim="):
            N = int(a.split("=")[1])
    arg = args[0] if args else "all"
    arenas = (["001", "002", "003", "004", "005"] if arg == "all"
              else ["mw001", "mw002", "mw003"] if arg == "mw" else [arg])
    for a in arenas:
        d = verify(a, N=N)
        v = d["verify"]; s = v["summary"]
        print("== %s  可信度 A%d/B%d/C%d/D%d  %.1fs  N=%d" % (
            a, s["A"], s["B"], s["C"], s["D"], v["secs"], v["n_sim"]))
        for p in d["points"][:6]:
            f = p["sim"]["follow"]
            print("  %2d) px(%4.0f,%4.0f) 稳态%d  conf %5.1f %s  达标%3.0f%% 可用%3.0f%% "
                  "P10=%.1f P50=%.1f 标注风险%4.1f  空%d" % (
                      p["no"], p["px"][0], p["px"][1], p["n_steady"], p["conf"], p["grade"],
                      f["hit_rate"] * 100, f["keep_rate"] * 100, f["p10"], f["p50"],
                      p["label_risk"], f["why"]["sky"] + f["why"]["off"]))


if __name__ == "__main__":
    main()
