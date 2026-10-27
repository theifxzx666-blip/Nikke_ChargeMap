# -*- coding: utf-8 -*-
"""汇总 35 章 7 张战场 × 5 个阵位的结果，输出 markdown 表格（写进文档用）。"""
import glob
import json
import os
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "导出")
ARENAS = ["001", "002", "003", "004", "005", "bbg008", "bbg009"]
VIEWS = ["cover_1", "cover_2", "cover_3", "cover_4", "cover_5"]


def load(a, v):
    p = os.path.join(OUT, "px_%s_%s.json" % (a, v))
    q = os.path.join(OUT, "audit_%s_%s.json" % (a, v))
    if not os.path.exists(p):
        return None, None
    d = json.load(open(p, encoding="utf-8"))
    au = None
    if os.path.exists(q):
        au = {r["no"]: r for r in json.load(open(q, encoding="utf-8"))["rows"]}
    return d, au


def med(vals):
    if not vals:
        return None
    vals = sorted(vals)
    return vals[len(vals) // 2]


def main():
    lines = []
    lines.append("| 战场 | 阵位 | 相机 x/z | 达标点 | 最高稳态 | 锥宽中位 | 审计 S/A/B/C/D |")
    lines.append("|---|---|---:|---:|---:|---:|---|")
    tot = Counter()
    per_arena = {}
    for a in ARENAS:
        for v in VIEWS:
            d, au = load(a, v)
            if not d:
                continue
            pts = d["points"]
            cones = [au[p["no"]]["cone_px"] for p in pts
                     if au and au.get(p["no"]) and au[p["no"]].get("cone_px")] if au else []
            grade = Counter(r["grade"] for r in au.values()) if au else Counter()
            tot.update(grade)
            n = len(pts)
            per_arena.setdefault(a, {})[v] = dict(n=n, top=max(
                [p["n_steady"] for p in pts], default=0),
                med=med(cones), grade=dict(grade))
            lines.append("| %s | %s | %.1f / %.1f | %d | %d | %s | %s |" % (
                a, v.replace("cover_", "") + " 号位" + ("（默认）" if v == "cover_3" else ""),
                d["cam"][0], d["cam"][2], n,
                max([p["n_steady"] for p in pts], default=0),
                ("%.1fpx" % med(cones)) if med(cones) else "—",
                " / ".join(str(grade.get(k, 0)) for k in "SABCD") if au else "—"))
    lines.append("")
    lines.append("合计审计分级：S%d / A%d / B%d / C%d / D%d（%d 个阵位）" % (
        tot.get("S", 0), tot.get("A", 0), tot.get("B", 0), tot.get("C", 0), tot.get("D", 0),
        sum(1 for a in ARENAS for v in VIEWS if load(a, v)[0])))
    txt = "\n".join(lines)
    open(os.path.join(BASE, "_views_table.md"), "w", encoding="utf-8").write(txt + "\n")
    print(txt)
    json.dump(per_arena, open(os.path.join(BASE, "_views_stat.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
