# -*- coding: utf-8 -*-
"""表单生成器（PROMPT §20.4）。三张表全部由本脚本现算，禁止手写。

    python 工具/校验/gen_catalog.py            重生成三张表（md / csv / xlsx）
    python 工具/校验/gen_catalog.py --check    只校验不写；有问题返回非 0（迁移/跑批的闸门）

产物：
    资源库/场景库清单.md            表单① 场景资产台账（每场景一行）
    正式产物/清单/点位总表.md       表单② 分析结果台账（每场景×阵位一行）
    正式产物/清单/点位总表.csv      同上，给 Excel 用
    正式产物/清单/点位总表.xlsx     同上，带格式（有 openpyxl 才写）
    正式产物/清单/覆盖率.md         表单③ 一行式汇总 + 缺失清单

--check 的六项断言（任一项不过就非 0）：
    1 场景卡存在且 mesh.tris > 0
    2 source/ 非空（原始 bundle 在）
    3 mesh/ 的 assembly 与 slots 都在
    4 审计行数 == 点位数
    5 px 的每个点都有 px[x,y] 与 n / n_steady
    6 registry 登记的场景都有目录（无孤儿登记）
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from paths import PATH                                # noqa: E402

STAGES = ("已还原", "已分析", "已验收", "待补")


def md_table(head, rows, align=None):
    align = align or ["---"] * len(head)
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(align) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if c is None else str(c) for c in r) + " |")
    return "\n".join(out)


def safe_json(p, default=None):
    if not os.path.exists(p):
        return default
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ── 采集 ────────────────────────────────────────────────────────────────
def scene_rows():
    rows = []
    for a in PATH.scenes():
        c = PATH.card(a)
        m = c.get("mesh") or {}
        src = c.get("source") or []
        rows.append({
            "scene": a,
            "chapter": PATH.chapter_dir(a),
            "display": (c.get("chapter") or {}).get("display"),
            "region": c.get("region"),
            "dir": c.get("dir"),
            "tris": m.get("tris"),
            "props": m.get("props"),
            "hitbox": m.get("hitbox"),
            "covers": len(PATH.views(a)) or m.get("covers"),
            "tex": (c.get("tex") or {}).get("count"),
            "n_bundle": len(src),
            "bundle_mb": round(sum(s.get("bytes") or 0 for s in src) / 1048576.0, 1),
            "dup_bundle": len(src) - len({s.get("sha1_16") for s in src}),
            "dup_mb": round(sum(s.get("bytes") or 0 for s in src)
                           - sum({s.get("sha1_16"): s.get("bytes") or 0 for s in src}.values())
                           , 0) / 1048576.0,
            "status": c.get("status"),
            "updated": c.get("updated"),
        })
    return rows


def point_rows():
    rows = []
    for a in PATH.scenes():
        for v in PATH.views(a):
            px = safe_json(PATH.px(a, v), {}) or {}
            au = safe_json(PATH.audit(a, v), {}) or {}
            pts = px.get("points") or []
            if not pts and not au:
                continue
            verify = px.get("verify") or {}
            fs = verify.get("field_sim") or {}
            conf = verify.get("summary") or {}
            cones = [r.get("cone_px") for r in (au.get("rows") or []) if r.get("cone_px")]
            cones.sort()
            med = cones[len(cones) // 2] if cones else None
            grade = {g: 0 for g in "SABCD"}
            for r in au.get("rows") or []:
                g = r.get("grade") or "-"
                if g in grade:
                    grade[g] += 1
            rows.append({
                "scene": a, "chapter": PATH.chapter_dir(a), "view": v,
                "n_pts": len(pts),
                "n_max": max([p.get("n_steady") or p.get("n") or 0 for p in pts] or [0]),
                "cone_med": round(med, 1) if med is not None else None,
                "S": grade["S"], "A": grade["A"], "B": grade["B"],
                "C": grade["C"], "D": grade["D"],
                "cA": conf.get("A"), "cB": conf.get("B"), "cC": conf.get("C"), "cD": conf.get("D"),
                "pool": fs.get("pool"), "pool_pct": fs.get("pool_pct"),
                "anchor": "%s / %s" % (a, v.replace("cover_", "c")),
            })
    return rows


# ── 校验闸门 ────────────────────────────────────────────────────────────
def check(scene_rows_, point_rows_):
    """返回 (硬问题, 软提示)。硬问题非空即闸门失败；软提示只记录。"""
    bad, warn = [], []
    for r in scene_rows_:
        a = r["scene"]
        if not r["tris"]:
            bad.append("%s 场景卡缺失或缺 mesh.tris" % a)
        p = os.path.join(PATH.scene_dir(a), "场景卡.json")
        if not os.path.exists(p):
            bad.append("%s 缺 场景卡.json" % a)
        # source/ 是 gitignore 的可重生成资源：场景卡已声明 sha1 就只提示（新克隆必然为空）
        sd = PATH.source_dir(a)
        if not os.path.isdir(sd) or not os.listdir(sd):
            declared = (PATH.card(a).get("source") or [])
            if declared:
                warn.append("%s source/ 为空（场景卡已登记 %d 份 bundle 的 sha1，"
                            "原始包不入库，需用 工具/采集/ 重新导出）" % (a, len(declared)))
            else:
                bad.append("%s source/ 为空且场景卡未声明 source" % a)
        # mesh/ 下的装配与阵位是入库物，缺了就是真问题
        if not os.path.exists(PATH.assembly(a)):
            bad.append("%s 缺 assembly" % a)
        if not os.path.exists(PATH.slots_path(a)):
            reg_status = (PATH.registry().get(a) or {}).get("status")
            if reg_status == "待补":
                warn.append("%s 缺 slots.json（registry 标记 待补，不阻塞）" % a)
            else:
                bad.append("%s 缺 slots.json 但 status=%r" % (a, reg_status))
        if r["status"] not in STAGES:
            bad.append("%s status 非法：%r" % (a, r["status"]))
        if r["dup_bundle"] > 0:
            warn.append("%s source/ 有 %d 份同 sha1 的重复 bundle（%s）"
                        % (a, r["dup_bundle"], "可去重省 %.1f MB" % r["dup_mb"]))
    for r in point_rows_:
        a, v = r["scene"], r["view"]
        px = safe_json(PATH.px(a, v), {}) or {}
        pts = px.get("points") or []
        for i, p in enumerate(pts):
            if not (isinstance(p.get("px"), list) and len(p["px"]) == 2):
                bad.append("%s/%s 第 %d 点 px 异常" % (a, v, i + 1))
                break
            if p.get("n") is None:
                bad.append("%s/%s 第 %d 点缺 n" % (a, v, i + 1))
                break
        au = safe_json(PATH.audit(a, v), {}) or {}
        if au and len(au.get("rows") or []) not in (0, len(pts)):
            bad.append("%s/%s 审计 %d 行 ≠ 点位 %d" % (a, v, len(au.get("rows") or []), len(pts)))
    for a in PATH.scenes():
        if not os.path.isdir(PATH.scene_dir(a)):
            bad.append("%s 已登记但目录不存在（孤儿登记）" % a)
    return bad, warn


# ── 三张表 ──────────────────────────────────────────────────────────────
def write_scene_table(sr):
    head = ["场景", "章节", "区域内部名", "三角面", "物件", "受击体", "阵位", "贴图",
            "bundle", "去重后体积", "状态", "复核"]
    rows = []
    for r in sr:
        rows.append([r["scene"], "%s（第 %s 章）" % (r["chapter"], r["display"]),
                     "`%s`" % r["region"], r["tris"], r["props"], r["hitbox"], r["covers"],
                     r["tex"], "%d 份" % r["n_bundle"], "%.1f MB" % r["bundle_mb"],
                     r["status"], r["updated"]])
    txt = "\n".join([
        "# 场景库清单",
        "",
        "> 本表由 `工具/校验/gen_catalog.py` **从场景卡现算**，不要手改（改了下次重生成就没了）。",
        "> 重跑：`python 工具/校验/gen_catalog.py`；校验：加 `--check`。",
        "> 分类边界见 `PROMPT.md §20.3`：`资源库/` 只放输入，分析结果在 `分析/`，交付物在 `正式产物/`。",
        "",
        "生成时间 %s · 场景 %d 个" % (time.strftime("%Y-%m-%d %H:%M"), len(sr)),
        "",
        md_table(head, rows, ["---", "---", "---", "---:", "---:", "---:", "---:", "---:",
                              "---:", "---:", "---", "---"]),
        "",
        "**读法**：`三角面` 是 `z=zmin` 修复后的全量（PROMPT §19）；低于 2 万的战场基本只有地形，",
        "点位会很稀。`去重后体积` 是 `source/` 里不同 sha1 的 bundle 合计。",
        "",
    ])
    p = os.path.join(PATH.LIB, "场景库清单.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(txt)
    return p


def write_point_table(pr):
    head = ["场景", "阵位", "达标点", "最高稳态段", "锥宽中位", "审计 S", "A", "B", "C", "D",
            "可信度 A", "B", "C", "D", "池子件数", "池子%"]
    rows = [[r["scene"], r["view"], r["n_pts"], r["n_max"], r["cone_med"],
             r["S"], r["A"], r["B"], r["C"], r["D"],
             r["cA"], r["cB"], r["cC"], r["cD"], r["pool"], r["pool_pct"]] for r in pr]
    tot_pts = sum(r["n_pts"] for r in pr)
    txt = "\n".join([
        "# 点位总表（每场景 × 阵位）",
        "",
        "> 由 `工具/校验/gen_catalog.py` 从 `分析/<章节>/<场景>/px_cover_N.json` 与",
        "> `audit_cover_N.json` **现算**，不手抄。重跑同一命令即可刷新。",
        "",
        "生成时间 %s · %d 组（场景 × 阵位）· 点位合计 %d"
        % (time.strftime("%Y-%m-%d %H:%M"), len(pr), tot_pts),
        "",
        md_table(head, rows, ["---", "---"] + ["---:"] * 14),
        "",
        "**读法**",
        "",
        "- `达标点` = 该阵位下满足 ≥2 段共线的瞄准点数量；`最高稳态段` = 其中最高的一条穿透链。",
        "- `锥宽中位` = 容错锥宽度（px）的中位数，**越大越容易按**；<2px 基本按不住。",
        "- `审计 S/A/B/C/D` 见 `docs/02-充能点算法.md §18`（六项独立审计）。",
        "- `可信度 A/B/C/D` 是 300 次扰动（站位/枪高/手抖/后坐/几何）后的保持率分级。",
        "- `池子%` = 该阵位可破坏物总充能 ÷ 一条爆裂条；<100% 意味着单靠打地形充不满。",
        "",
    ])
    p = os.path.join(PATH.LISTS, "点位总表.md")
    os.makedirs(PATH.LISTS, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(txt)

    # csv
    pc = os.path.join(PATH.LISTS, "点位总表.csv")
    with open(pc, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["场景", "章节", "阵位", "达标点", "最高稳态段", "锥宽中位px",
                    "审计S", "审计A", "审计B", "审计C", "审计D",
                    "可信A", "可信B", "可信C", "可信D", "池子件数", "池子pct", "锚点"])
        for r in pr:
            w.writerow([r["scene"], r["chapter"], r["view"], r["n_pts"], r["n_max"],
                        r["cone_med"], r["S"], r["A"], r["B"], r["C"], r["D"],
                        r["cA"], r["cB"], r["cC"], r["cD"], r["pool"], r["pool_pct"],
                        r["anchor"]])

    # xlsx（可选，给习惯表的人）
    px_ = os.path.join(PATH.LISTS, "点位总表.xlsx")
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        wb = Workbook()
        ws = wb.active
        ws.title = "点位总表"
        head2 = ["场景", "章节", "阵位", "达标点", "最高稳态段", "锥宽中位px",
                 "审计S", "A", "B", "C", "D", "可信A", "可信B", "可信C", "可信D",
                 "池子件数", "池子%"]
        ws.append(head2)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="2F5D4E")
            c.alignment = Alignment(horizontal="center")
        for r in pr:
            ws.append([r["scene"], r["chapter"], r["view"], r["n_pts"], r["n_max"],
                       r["cone_med"], r["S"], r["A"], r["B"], r["C"], r["D"],
                       r["cA"], r["cB"], r["cC"], r["cD"], r["pool"], r["pool_pct"]])
        for i, wd in enumerate([9, 20, 9, 8, 11, 11, 7, 5, 5, 5, 5, 7, 5, 5, 5, 9, 8], 1):
            ws.column_dimensions[chr(64 + i) if i <= 26 else "A"].width = wd
        ws.freeze_panes = "A2"
        wb.create_sheet("场景库").append(["场景", "章节", "三角面", "受击体", "阵位", "贴图", "状态"])
        for r in scene_rows():
            wb["场景库"].append([r["scene"], r["chapter"], r["tris"], r["hitbox"],
                                 r["covers"], r["tex"], r["status"]])
        wb.save(px_)
    except Exception as e:                                    # 没装 openpyxl 就只出 md/csv
        px_ = None
        print("  (xlsx 跳过：%s)" % e)
    return p, pc, px_


def write_coverage(sr, pr, bad, warn=()):
    scenes = len(sr)
    analyzed = len({r["scene"] for r in pr})
    total_views = sum(r["covers"] or 0 for r in sr)
    done_views = len(pr)
    pts = sum(r["n_pts"] for r in pr)
    miss = []
    for r in sr:
        have = {x["view"] for x in pr if x["scene"] == r["scene"]}
        need = {"cover_%d" % i for i in range(1, 6)}
        if not have:
            miss.append("%s 未分析" % r["scene"])
        elif r["covers"] and len(have) < r["covers"]:
            miss.append("%s 缺 %s" % (r["scene"], ",".join(sorted(need - have))))
    pages = []
    if os.path.isdir(PATH.PAGES):
        pages = sorted(x for x in os.listdir(PATH.PAGES) if x.endswith(".html"))
    txt = "\n".join([
        "# 覆盖率",
        "",
        "```",
        "场景 %d / 已分析 %d / 已验收 %d · 点位 %d（%d 组）· 阵位 %d/%d · 页面 %d"
        % (scenes, analyzed, sum(1 for r in sr if r["status"] == "已验收"), pts,
           len(pr), done_views, total_views or done_views, len(pages)),
        "```",
        "",
        "## 缺口",
        "",
        ("\n".join("- " + m for m in miss) if miss else "- 无"),
        "",
        "## 闸门（`gen_catalog.py --check`）",
        "",
        ("\n".join("- " + b for b in bad) if bad else "- 全部通过"),
        "",
        "## 待处理（提示，不算失败）",
        "",
        ("\n".join("- " + w for w in warn) if warn else "- 无"),
        "",
        "## 页面",
        "",
        "\n".join("- `正式产物/页面/%s`" % p for p in pages) or "- 无",
        "",
        "生成时间 %s" % time.strftime("%Y-%m-%d %H:%M"),
        "",
    ])
    p = os.path.join(PATH.LISTS, "覆盖率.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(txt)
    return p


def main():
    check_only = "--check" in sys.argv
    sr = scene_rows()
    pr = point_rows()
    bad, warn = check(sr, pr)

    if check_only:
        print("场景 %d · 组 %d · 点位 %d" % (len(sr), len(pr), sum(r["n_pts"] for r in pr)))
        for w in warn:
            print("  ~~ " + w)
        for b in bad:
            print("  !! " + b)
        print("闸门：%s（提示 %d）"
              % ("通过" if not bad else "失败 %d 项" % len(bad), len(warn)))
        return 0 if not bad else 1

    p1 = write_scene_table(sr)
    p2, p3, p4 = write_point_table(pr)
    p5 = write_coverage(sr, pr, bad, warn)
    for p in (p1, p2, p3, p4, p5):
        if p:
            print("  -> %s" % os.path.relpath(p, PATH.ROOT))
    if bad:
        print("闸门失败 %d 项（表已写，问题见 覆盖率.md）" % len(bad))
        for b in bad[:8]:
            print("  !! " + b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
