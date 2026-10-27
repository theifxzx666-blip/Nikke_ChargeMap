#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""sim_charge.py — 时间轴充能模拟：从「单点段数」升级为「战场轮换路径」。

【为什么必须改】
px_*.json 的 n_steady = medium + hard，假设「soft 一打就碎、中/硬永不碎」。
但 ConfigBattleTable 三档全是 HP（soft 100 / medium 500 / hard 1000），
hpdamage_limit=30 语义未定，于是碎裂时序有两种都合法的解释：

    A 无上限   单发伤害(数千~数万) >> 1000 → 一枪全碎
    B 上限 30  每发最多扣 30 → soft 4 发 / medium 17 发 / hard 34 发才碎

第一次按「单点充满」模拟时，A 模式下 shots=1 就停了 —— 因为整个方向被一枪打空，
再也拿不到任何充能。这不是 bug，它说明：**碎裂后受击物是从场景里消失的，而且跨点位共享**。
所以「充满一条爆裂条」在 A 模式下根本不可能由单点完成，必须**在多个点位之间轮换**。

⇒ 正确的模型是「战场级轮换」：
    维护全局已碎集合 → 按顺序消耗点位 → 逐发结算（先给充能，再扣血）
    直到爆裂条满（或所有点位耗尽）

【两个指标】
    shots_total : 充满需要几发（A/B 两种假设各一个值，取差的做排序 = 稳健优化）
    pts_used    : 用到几个点位（A 模式下这才是「点位数量」的真正价值）
    short       : 所有点位轮完仍充不满（说明该战场目标总量不足）

【为什么是「算法优化」而不只是「换个数字」】
点位之间共享受击物：A 打掉 3 件，B 就少 3 段。所以按「单点段数」排序不是最优 ——
应该按「当前剩余目标下的边际贡献」排序（贪心集合覆盖）。
脚本同时跑「原排序」与「贪心重排」，量化顺序优化能省几发。

用法：
    python sim_charge.py mw003
    python sim_charge.py all
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "导出")

BAR = 10000          # 爆裂条显示口径（burst_energy_max / 100）
PER_SEG = 280        # 小红帽 SR 单发充能（2.80% × 10000）
MAX_SHOTS = 600

# field_*_fire_speed_rate = 射击间隔（秒/发）。量级自检：
#   SR 1.2→0.83/s · AR 0.18→5.6/s · SMG 0.15→6.7/s · MG 0.25→4/s · SG 0.8→1.25/s · RL 1.8→0.56/s
RATE = {"AR": 0.18, "SG": 0.8, "RL": 1.8, "MG": 0.25, "SR": 1.2, "SMG": 0.15}
SWAMP = ["001", "002", "003", "004", "005"]


def _hits(pt):
    """该点穿透的件（按距离升序）。用 name 作为跨点位共享的物体身份。"""
    return sorted((h for h in (pt.get("detail") or []) if h.get("name")),
                  key=lambda h: h.get("d", 0))


def run_field(points, mode, dmg=10000.0, limit=30.0, greedy=False):
    """战场级轮换模拟。返回 dict(shots, pts, short, left, log, order)。"""
    dmg_i = dmg if mode == "A" else min(dmg, limit)
    alive = {}
    for pt in points:
        for h in _hits(pt):
            alive.setdefault(h["name"], float(h.get("hp") or 100))

    need, shots, used, log, order = BAR, 0, 0, [], []
    pool = list(points)
    while need > 0 and pool and shots < MAX_SHOTS:
        if greedy:      # 贪心：选「当前仍有最多新鲜件」的点（集合覆盖）
            pt = max(pool, key=lambda p: sum(1 for h in _hits(p) if alive.get(h["name"], 0) > 0))
        else:
            pt = pool[0]
        pool.remove(pt)

        hits = _hits(pt)
        if not any(alive.get(h["name"], 0) > 0 for h in hits):
            continue                                    # 全被打碎了，跳过不计数
        used += 1
        order.append(pt.get("no"))
        while need > 0:
            live = [h for h in hits if alive.get(h["name"], 0) > 0]
            if not live:
                break
            gain = len(live) * PER_SEG
            need -= gain
            shots += 1
            log.append((pt.get("no"), len(live), gain))
            for h in live:
                alive[h["name"]] = alive.get(h["name"], 0) - dmg_i
            if shots >= MAX_SHOTS:
                break
    return dict(shots=shots, pts=used, short=(need > 0), left=max(0, need),
                log=log, order=order)


def point_yield(pt, mode, dmg=10000.0, limit=30.0):
    """单点（新鲜状态、独占使用）能给出多少充能 —— 仅作参考列，不是主指标。"""
    dmg_i = dmg if mode == "A" else min(dmg, limit)
    hp = [float(h.get("hp") or 100) for h in _hits(pt)]
    seq, tot = [], 0
    while True:
        idx = [i for i in range(len(hp)) if hp[i] > 0]
        if not idx or len(seq) > MAX_SHOTS:
            break
        seq.append(len(idx))
        tot += len(idx) * PER_SEG
        for i in idx:
            hp[i] -= dmg_i
    return dict(charge=tot, pct=round(tot / 100.0, 2),
                seq=seq[:14], shots=len(seq),
                drop=(seq[0] - seq[-1]) if seq else 0)


def run(arenas, weapon="SR", dmg=10000.0, limit=30.0, write=True, view=None):
    dt = RATE.get(weapon, 1.2)
    out = []
    for a in arenas:
        fn = ("px_%s_%s.json" % (a, view)) if view else ("px_%s.json" % a)
        p = os.path.join(OUT, fn)
        if not os.path.exists(p):
            print("  !! 缺 %s" % p)
            continue
        d = json.load(open(p, encoding="utf-8"))
        pts = d["points"]

        if not pts:
            # 0 个达标点的阵位（bbg008 的 1/2/3 号位就是这种）。原来这里直接
            # pts[0] 会 IndexError 把整组判失败 —— 空战场也是合法结果，写全 0 就行。
            d.setdefault("verify", {})["field_sim"] = dict(
                weapon=weapon, sec_per_shot=dt, per_shot_dmg=dmg, limit=limit,
                per_seg=PER_SEG, bar=BAR, n_points=0, pool=0, pool_pct=0.0,
                A=dict(shots=0, pts=0, short=0, t=0.0, order=[], order_greedy=[]),
                B=dict(shots=0, pts=0, short=0, t=0.0, order=[], order_greedy=[]),
                greedy_A=dict(shots=0, pts=0, short=0),
                greedy_B=dict(shots=0, pts=0, short=0),
                gain_A=0, gain_B=0,
            )
            if write:
                json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
            out.append((a, d))
            print("== %-6s  0 点（该阵位没有达标点，轮换为空）" % a)
            continue

        # ① 原排序（单点段数优先）下的轮换
        ra = run_field(pts, "A", dmg, limit, greedy=False)
        rb = run_field(pts, "B", dmg, limit, greedy=False)
        # ② 贪心重排（边际贡献优先）后的轮换
        ga = run_field(pts, "A", dmg, limit, greedy=True)
        gb = run_field(pts, "B", dmg, limit, greedy=True)

        # 单点产出（参考列）
        for pt in pts:
            pt["time"] = dict(
                a=point_yield(pt, "A", dmg, limit),
                b=point_yield(pt, "B", dmg, limit),
                weapon=weapon, sec_per_shot=dt,
            )

        # 点位命中集合的并集 = 该战场可破坏物「池子」（A 模式下总充能上限 = 池子 × 280）
        names = {h["name"] for pt in pts for h in _hits(pt)}
        pool = len(names)
        pool_pct = round(pool * PER_SEG / 100.0, 1)

        d.setdefault("verify", {})["field_sim"] = dict(
            weapon=weapon, sec_per_shot=dt, per_shot_dmg=dmg, limit=limit,
            per_seg=PER_SEG, bar=BAR, n_points=len(pts),
            pool=pool, pool_pct=pool_pct,
            A=dict(shots=ra["shots"], pts=ra["pts"], short=ra["short"],
                   t=round(ra["shots"] * dt, 1), order=ra["order"],
                   order_greedy=ga["order"]),
            B=dict(shots=rb["shots"], pts=rb["pts"], short=rb["short"],
                   t=round(rb["shots"] * dt, 1), order=rb["order"],
                   order_greedy=gb["order"]),
            greedy_A=dict(shots=ga["shots"], pts=ga["pts"], short=ga["short"]),
            greedy_B=dict(shots=gb["shots"], pts=gb["pts"], short=gb["short"]),
            gain_A=ra["shots"] - ga["shots"],
            gain_B=rb["shots"] - gb["shots"],
        )
        if write:
            json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        out.append((a, d))

        fs = d["verify"]["field_sim"]
        print("== %-6s %2d 点 池%3d件(%4.0f%%) | A: %2d 发/%2d 点%s | B: %2d 发/%2d 点 | 贪心省 A%d B%d" % (
            a, fs["n_points"], pool, pool_pct,
            fs["A"]["shots"], fs["A"]["pts"], " ✗不够" if fs["A"]["short"] else "",
            fs["B"]["shots"], fs["B"]["pts"],
            fs["gain_A"], fs["gain_B"]))
    return out


def report(rows):
    print("\n%-6s %-4s %-4s %-8s %-9s %-7s %-6s" % (
        "战场", "点数", "首轮", "单点A", "单点B", "充满A", "充满B"))
    for a, d in rows:
        fs = d["verify"]["field_sim"]
        if not d["points"]:                 # 0 点的阵位（bbg008 部分机位）
            print("%-6s %-4d %-4s %-8s %-9s %-7d %-6d" % (a, 0, "—", "—", "—", 0, 0))
            continue
        p0 = d["points"][0]["time"]
        print("%-6s %-4d %-4d %-8s %-9s %-7d %-6d" % (
            a, fs["n_points"], p0["a"]["seq"][0] if p0["a"]["seq"] else 0,
            "%d发/%d%%" % (p0["a"]["shots"], round(p0["a"]["pct"])),
            "%d发/%d%%" % (p0["b"]["shots"], min(999, round(p0["b"]["pct"]))),
            fs["A"]["shots"], fs["B"]["shots"]))
    tot = sum(len(d["points"]) for _, d in rows)
    print("\n点位合计 %d 个；A 模式平均需 %.1f 个点轮换，B 模式 %.1f 个" % (
        tot,
        sum(d["verify"]["field_sim"]["A"]["pts"] for _, d in rows) / max(1, len(rows)),
        sum(d["verify"]["field_sim"]["B"]["pts"] for _, d in rows) / max(1, len(rows))))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    arg = args[0] if args else "mw"
    weapon = opts.get("weapon", "SR")
    dmg = float(opts.get("dmg", 10000))
    limit = float(opts.get("limit", 30))
    no_write = "--no-write" in sys.argv
    view = opts.get("view") or None

    arenas = sorted(SWAMP) if arg == "all" else (
        ["mw001", "mw002", "mw003"] if arg == "mw" else [arg])
    rows = run(arenas, weapon=weapon, dmg=dmg, limit=limit, write=not no_write, view=view)
    report(rows)


if __name__ == "__main__":
    main()
