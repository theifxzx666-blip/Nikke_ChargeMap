# -*- coding: utf-8 -*-
"""全量战场采集编排器 —— 一条命令把「客户端里所有战斗场景」拉进场景库。

背景（为什么是「扫描式」而不是「按章节采」）：
  客户端**没有**「关卡 → 背景」的映射表（见 docs/09 §6 缺口 1）。所以拿不到
  「第 42 章用哪张图」。能拿到的只有全集：catalog 里 174 个 `spotbackground(hd)`。
  因此本工具的做法是把全集按优先级扫下来，章节归属留待人工认图后归档。

三级优先级（分级规则在 classify()，可改）：
  P1 主战场   `sbg_<区域>_<NNN>`  主线战斗真正用的背景，先采这批
  P2 boss     `bbg / mbg / ebg / cabal`  boss 与布景专场
  P3 变体     `_rightclear / _midclear / _sky / _b / _oc / custom / fly …`
              同一场景的清除/天空/特殊位变体，点位通常与主场景共享，可不采

单个场景的完整链路（每步失败只记错，不中断整批）：
  1 extract   adb 取 bundle           → <场景>/source/
  2 card      写 场景卡.json            （source 段登记 sha1_16）
  3 registry  登记 registry.json        （之后 PATH.* 才认这个场景）
  4 assembly  build_assembly.py        → <场景>/mesh/assembly_<id>.json
  5 tex       dump_tex.py              → <场景>/tex/*.png + index.json
  6 glb       export_glb.py            → <场景>/mesh/arena_<id>.glb
  7 slots     build_slots.build()      → <场景>/mesh/slots.json
  8 recard    回填 tris/props/hitbox/covers/tex.count，status → 已还原

用法：
  python collect_all.py --preflight                  # 查 catalog / cdb.idx / adb
  python collect_all.py --list [--tier 1,2]          # 看全集与已采状态
  python collect_all.py --plan                       # 落 分析/_采集计划.csv
  python collect_all.py --run --tier 1               # 采 P1 主战场
  python collect_all.py --run --tier 1,2 --jobs 1    # P1+P2（adb 单设备，必须串行）
  python collect_all.py --run --only sj001,gh002     # 只跑指定短名
  python collect_all.py --run --tier 1 --chapter H36_某某   # 指定章节目录
  python collect_all.py --stage tex --only sj001     # 只补某一阶段

断点续跑：默认看 `<场景>/mesh/assembly_<id>.json` 在不在，在就跳过；`--force` 重跑。
进度表：`分析/_采集进度.csv`（每次 --run 追加一行，含耗时与错误摘要）。
"""
import argparse
import collections
import csv
import glob
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)

import extract_core as ec                                  # noqa: E402
from paths import PATH                                     # noqa: E402

PY = sys.executable
PENDING_CHAPTER = "H00_待归档"          # 章节未知时的落位（认图后改名，见 §20.2 S4）
PROGRESS = os.path.join(PATH.ANA, "_采集进度.csv")

# ── 区域 → 短名缩写（最长前缀匹配，顺序无关）──────────────────────────────
REGION_ABBR = {
    "swamplandjungle": "sj",
    "cityforestundercrystal": "cc",
    "cityforestunderelevator": "ce",
    "cityforestunder": "cu",
    "cityforest": "cf",
    "motherwhalefield": "mw",
    "whitearkcity": "wc",
    "arkcityday": "ay",
    "arkcity": "ac",
    "arkout": "ao",
    "desertcrystal": "dc",
    "desert": "ds",
    "greathole": "gh",
    "iceland": "ic",
    "lostsector": "ls",
    "ocean": "oc",
    "redoceanfarsea": "rf",
    "redocean": "ro",
    "simulation": "sm",
    "surface": "sf",
    "tower": "tw",
    "volcano": "vc",
    "wasteland": "wl",
    "gravedigger": "gd",
}

# 变体后缀 → 短名后缀（只为了让目录名不至于长得没法看）
SUF_ABBR = {"rightclear": "r", "midclear": "m", "custom": "c", "escape": "esc", "rich": "rich"}
PRE_ABBR = {"escape": "esc", "custom": "cus", "sky": "sky"}


# ── 写盘 helper ──────────────────────────────────────────────────────────
def _save(obj, path):
    """paths.write_json 的签名是 (obj, path)，与直觉相反，统一走这里避免写反。"""
    return PATH.write_json(obj, path)


REG_PATH = os.path.join(PATH.LIB, "registry.json")


def _save_registry(reg):
    """registry.json 外层是 {"scenes": {...}}；写完必须清模块缓存，
    否则同一进程里 PATH.registry() 还返回写之前的旧 dict。"""
    PATH.write_json({"scenes": reg}, REG_PATH)
    PATH._reg = None


# ── 分级 ────────────────────────────────────────────────────────────────
def classify(stem):
    """stem 不含 `sbg_` 前缀。返回 (tier, 标签)。"""
    s = stem
    if re.search(r"(rightclear|midclear)$", s):
        return 3, "清除变体"
    if "_sky_" in s or s.endswith("_sky") or s.startswith("skyfall"):
        return 3, "天空盒"
    if re.search(r"(bbg|mbg|ebg|cabal)", s):
        return 2, "boss/布景"
    if re.search(r"_(custom|fly|escape)$", s):
        return 3, "特殊位"
    if re.search(r"_(fly|b|escape|custom)_\d", s):
        return 3, "特殊位"
    if re.search(r"(xbg|xba|eba|bba|_rich)", s):
        return 3, "特殊位"
    if re.search(r"_b_|_oc$", s):
        return 3, "特殊位"
    return 1, "主战场"


def region_of(stem):
    best = ""
    for k in REGION_ABBR:
        if stem.startswith(k) and len(k) > len(best):
            best = k
    if best:
        return best
    return re.sub(r"(_\d{3}.*|(bbg|mbg|ebg|bba|xba|xbg|eba)\d{3}.*)$", "", stem) or stem


def short_name(stem, region):
    """生成 registry 键（= 目录名前缀）。要求全局唯一，见 finalize_names()。"""
    ab = REGION_ABBR.get(region) or re.sub(r"[^a-z]", "", region)[:2]
    tail = stem[len(region):].replace("_", "")
    m = re.match(r"([a-z]*)(\d{3})(.*)$", tail)
    if not m:
        return ab + re.sub(r"[^a-z0-9]", "", tail)[:6]
    pre, num, suf = m.group(1), m.group(2), m.group(3)
    pre = PRE_ABBR.get(pre, pre)
    suf = SUF_ABBR.get(suf, suf)
    return ab + pre + num + suf


# ── catalog 扫描 ─────────────────────────────────────────────────────────
def scan_catalog(verbose=False):
    """返回 [{stem, region, short, tier, label, file_id, key}]，按 tier/stem 排序。"""
    if not os.path.exists(ec.CATALOG):
        raise SystemExit("缺少 catalog：%s\n先用 decrypt_nkdb.py 解一份，或从旧机拷过来。"
                         % ec.CATALOG)
    con = sqlite3.connect("file:%s?mode=ro" % ec.CATALOG.replace("\\", "/"), uri=True)
    rows = list(con.execute(
        "select file_id, key from files_chunktype where key like '%spotbackground(hd)%' "
        "order by key"))
    con.close()

    out, seen = [], {}
    for fid, key in rows:
        base = key.split("/")[-1]
        m = re.match(r"spotbackground\(hd\)_assets_(.+)\.bundle$", base)
        if not m:
            continue
        stem = re.sub(r"_[0-9a-f]{32}$", "", m.group(1))
        if not stem.startswith("sbg_"):
            continue
        body = stem[4:]
        region = region_of(body)
        tier, label = classify(body)
        short = short_name(body, region)
        if short in seen:                                   # 理论不该撞，撞了加后缀
            n = 2
            while "%s_%d" % (short, n) in seen:
                n += 1
            short = "%s_%d" % (short, n)
        seen[short] = stem
        out.append(dict(stem=stem, body=body, region=region, short=short,
                        tier=tier, label=label, file_id=fid, key=key, base=base))
    out.sort(key=lambda r: (r["tier"], r["stem"]))
    if verbose:
        c = collections.Counter(r["tier"] for r in out)
        print("catalog 命中 hd 主场景 %d 个：P1=%d  P2=%d  P3=%d"
              % (len(out), c[1], c[2], c[3]))
    return out


def existing_scenes():
    """已登记场景 → {arena_bundle全名: registry键}，用于跳过重复采集。"""
    reg = PATH.registry()
    return {v.get("arena") or k: k for k, v in reg.items()}


# ── 落位 ────────────────────────────────────────────────────────────────
def scene_paths(short, chapter_dir):
    d = os.path.join(PATH.LIB, chapter_dir, "%s_%s" % (short, ""))  # 占位，稍后拼 full
    return d


def make_scene(item, chapter_dir, chapter_meta=None):
    """建目录 + 写场景卡 + 登记 registry。返回 (dir_abs, dir_name)。"""
    dname = "%s_%s" % (item["short"], item["body"])
    dabs = os.path.join(PATH.LIB, chapter_dir, dname)
    for sub in ("source", "mesh", "tex"):
        os.makedirs(os.path.join(dabs, sub), exist_ok=True)

    # --- 章节卡（每章一份，缺就建）
    cpath = os.path.join(PATH.LIB, chapter_dir, "_章节.json")
    if not os.path.exists(cpath):
        meta = chapter_meta or {"display": 0, "chapter_id": 0, "name": chapter_dir.split("_", 1)[-1],
                                "region": item["region"], "verified": None}
        meta.update({"dir": chapter_dir, "scenes": []})
        _save(meta, cpath)

    # --- 场景卡
    card_path = os.path.join(dabs, "场景卡.json")
    card = {}
    if os.path.exists(card_path):
        try:
            card = json.load(open(card_path, encoding="utf-8"))
        except Exception:
            card = {}
    card.setdefault("scene_id", item["short"])
    card["chapter_dir"] = chapter_dir
    card["dir"] = dname
    card["region"] = item["region"]
    card["arena"] = item["stem"]
    card.setdefault("source", [])
    card.setdefault("mesh", {})
    card.setdefault("tex", {"dir": "tex", "count": 0})
    card["status"] = card.get("status") or "已采"
    card["updated"] = time.strftime("%Y-%m-%d")
    _save(card, card_path)

    # --- registry
    reg = PATH.registry()
    reg[item["short"]] = {
        "chapter_dir": chapter_dir,
        "dir": dname,
        "region": item["region"],
        "arena": item["stem"],
        "status": card["status"],
        "updated": card["updated"],
    }
    _save_registry(reg)

    # --- 章节卡的 scenes 列表补齐
    ch = json.load(open(cpath, encoding="utf-8"))
    if item["short"] not in ch.get("scenes", []):
        ch.setdefault("scenes", []).append(item["short"])
        ch["scenes"].sort()
        _save(ch, cpath)

    return dabs, dname


def register_source(short, bundle_name, nbytes):
    p = PATH.card(short)
    sha = hashlib.sha1(open(os.path.join(PATH.source_dir(short), bundle_name), "rb").read()) \
        .hexdigest()[:16]
    src = [s for s in (p.get("source") or []) if s.get("file") != bundle_name]
    src.append({"file": bundle_name, "bytes": nbytes, "sha1_16": sha})
    p["source"] = sorted(src, key=lambda s: s["file"])
    _save(p, os.path.join(PATH.scene_dir(short), "场景卡.json"))


def recount(short, extra=None):
    """回填 mesh/tex 统计，status → 已还原。"""
    p = PATH.card(short)
    try:
        asm = json.load(open(PATH.assembly(short), encoding="utf-8"))
    except Exception:
        asm = {}
    tris = sum(len(x.get("i") or []) // 3 for x in asm.get("props") or [])
    mesh = dict(p.get("mesh") or {})
    mesh.update({
        "assembly": os.path.basename(PATH.assembly(short)),
        "glb": os.path.basename(PATH.glb(short)),
        "meta": os.path.basename(PATH.meta(short)),
        "slots": "slots.json",
        "tris": tris,
        "props": len(asm.get("props") or []),
        # hitbox = 碰撞档位三层（hard/medium/soft）。实测与既有 16 个场景卡数值吻合
        # （如 sj001：35+28+80=143），不是 props 上的某个字段。
        "hitbox": sum(1 for x in asm.get("props") or []
                      if x.get("g") in ("hard", "medium", "soft")),
        "covers": len(PATH.views(short)),
    })
    if extra:
        mesh.update(extra)
    p["mesh"] = mesh
    td = PATH.tex_dir(short)
    p["tex"] = {"dir": "tex",
                "count": len([f for f in os.listdir(td) if f.endswith(".png")])
                if os.path.isdir(td) else 0}
    if mesh["tris"] and p.get("status") in ("已采", "待补"):
        p["status"] = "已还原"
    p["updated"] = time.strftime("%Y-%m-%d")
    _save(p, os.path.join(PATH.scene_dir(short), "场景卡.json"))

    reg = PATH.registry()
    if short in reg:
        reg[short]["status"] = p["status"]
        reg[short]["updated"] = p["updated"]
        _save_registry(reg)


# ── 单场景全流程 ─────────────────────────────────────────────────────────
STAGES = ("extract", "card", "registry", "assembly", "tex", "glb", "slots", "recard")


def run_one(item, chapter_dir, stages=STAGES, force=False, chapter_meta=None, log=print):
    """跑一个场景。返回 dict(short, ok, secs, stage, err)。"""
    short, stem = item["short"], item["stem"]
    t0 = time.time()
    state = {"short": short, "stem": stem, "tier": item["tier"], "ok": False,
             "stage": "-", "err": "", "secs": 0.0, "bundle_mb": 0.0, "tris": 0}

    try:
        # 0 已采则跳过（看 assembly 在不在）
        if not force and os.path.exists(os.path.join(
                PATH.LIB, chapter_dir, "%s_%s" % (short, item["body"]), "mesh",
                "assembly_%s.json" % short)):
            state.update(ok=True, stage="skip")
            log("  跳过 %-10s 已有装配" % short)
            return state

        # 1 extract
        dabs, dname = make_scene(item, chapter_dir, chapter_meta)
        src_dir = os.path.join(dabs, "source")
        bname = "%s.bundle" % stem
        bpath = os.path.join(src_dir, bname)
        state["stage"] = "extract"
        if force or not os.path.exists(bpath):
            con = sqlite3.connect(ec.CATALOG)
            if ec._IDX_POS is None:
                ec.load_idx()
            n, dbg = ec.extract(item["file_id"], bpath, con)
            con.close()
            state["bundle_mb"] = n / 1e6
            log("  取包 %-10s %7.2f MB  %s  %s"
                % (short, n / 1e6, open(bpath, "rb").read(6).decode("ascii", "replace"),
                   dbg[:1]))
        else:
            state["bundle_mb"] = os.path.getsize(bpath) / 1e6
            log("  取包 %-10s 已有 %7.2f MB（--force 可重取）"
                % (short, state["bundle_mb"]))

        # 2 card（source 段登记）
        state["stage"] = "card"
        register_source(short, bname, os.path.getsize(bpath))

        # 4 assembly
        state["stage"] = "assembly"
        asm_p = PATH.assembly(short)
        if force or not os.path.exists(asm_p):
            r = subprocess.run([PY, os.path.join(TOOLS, "还原", "build_assembly.py"),
                                bpath, asm_p], capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            if r.returncode != 0 or not os.path.exists(asm_p):
                raise RuntimeError("build_assembly 失败：%s" % (r.stderr or "")[-400:])

        # 5 tex
        state["stage"] = "tex"
        if force or not os.path.isdir(PATH.tex_dir(short)) or \
                len(glob.glob(os.path.join(PATH.tex_dir(short), "*.png"))) == 0:
            import dump_tex as dt
            dt.dump_arena(short, quiet=True)

        # 6 glb
        state["stage"] = "glb"
        if force or not os.path.exists(PATH.glb(short)):
            r = subprocess.run([PY, os.path.join(TOOLS, "还原", "export_glb.py"), short],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
            if r.returncode != 0 or not os.path.exists(PATH.glb(short)):
                raise RuntimeError("export_glb 失败：%s" % (r.stderr or "")[-400:])

        # 7 slots
        state["stage"] = "slots"
        sp = PATH.slots_path(short)
        if force or not os.path.exists(sp):
            import build_slots as bs
            s = bs.build(bpath)
            _save({short: s} if s else {}, sp)

        # 8 recard
        state["stage"] = "recard"
        recount(short)
        card = PATH.card(short)
        state["tris"] = (card.get("mesh") or {}).get("tris") or 0
        state["ok"] = True
        log("  完成 %-10s tris=%-6s covers=%-2s tex=%-4s %.1fs"
            % (short, state["tris"], (card.get("mesh") or {}).get("covers"),
               (card.get("tex") or {}).get("count"), time.time() - t0))

    except Exception as e:
        state["err"] = "%s: %s" % (state["stage"], str(e).replace("\n", " ")[:300])
        log("  !! %-10s %s" % (short, state["err"]))

    state["secs"] = round(time.time() - t0, 1)
    return state


# ── 进度表 ──────────────────────────────────────────────────────────────
def append_progress(rows):
    os.makedirs(os.path.dirname(PROGRESS), exist_ok=True)
    new = not os.path.exists(PROGRESS)
    cols = ["time", "short", "stem", "tier", "ok", "stage", "secs", "bundle_mb", "tris", "err"]
    with open(PROGRESS, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({"time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        **{k: r.get(k, "") for k in cols if k != "time"}})
    return PROGRESS


def read_progress():
    if not os.path.exists(PROGRESS):
        return {}
    out = {}
    with open(PROGRESS, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if str(r.get("ok")).lower() == "true" or r.get("ok") is True:
                out[r["short"]] = r
    return out


# ── 命令 ────────────────────────────────────────────────────────────────
def cmd_preflight(args):
    bad = ec.preflight(need_adb=True)
    print()
    print("catalog  : %s" % ec.CATALOG)
    print("cdb.idx  : %s" % ec.IDX_PATH)
    print("STORE    : %s" % ec.STORE)
    if bad:
        print("\n未通过 %d 项，先修复再采。" % len(bad))
        return 1
    items = scan_catalog(verbose=True)
    print("预计体积：P1 %.1f GB / P2 %.1f GB / P3 %.1f GB（按单场景 9 MB 粗算）"
          % (sum(1 for i in items if i["tier"] == 1) * 9 / 1024,
             sum(1 for i in items if i["tier"] == 2) * 9 / 1024,
             sum(1 for i in items if i["tier"] == 3) * 9 / 1024))
    return 0


def pick(args):
    items = scan_catalog()
    if args.tier:
        want = set(int(x) for x in str(args.tier).split(","))
        items = [i for i in items if i["tier"] in want]
    if args.only:
        want = set(x.strip() for x in args.only.split(",") if x.strip())
        items = [i for i in items if i["short"] in want or i["stem"] in want]
    return items


def cmd_list(args):
    items = pick(args)
    done = existing_scenes()
    prog = read_progress()
    print("%-12s %-3s %-9s %-34s %-8s %s"
          % ("短名", "级", "标签", "bundle 主干", "状态", "tris"))
    print("-" * 86)
    stat = collections.Counter()
    for i in items:
        st = "已采" if i["stem"] in done else ("已跑" if i["short"] in prog else "—")
        stat[st] += 1
        print("%-12s P%-2d %-9s %-34s %-8s %s"
              % (i["short"], i["tier"], i["label"], i["body"], st,
                 (prog.get(i["short"], {}) or {}).get("tris", "") if st == "已跑" else ""))
    print("-" * 86)
    print("共 %d 个：已采 %d / 已跑 %d / 待采 %d"
          % (len(items), stat["已采"], stat["已跑"], stat["—"]))
    return 0


def cmd_plan(args):
    items = pick(args)
    done = existing_scenes()
    os.makedirs(PATH.ANA, exist_ok=True)
    p = os.path.join(PATH.ANA, "_采集计划.csv")
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["短名", "级别", "标签", "区域", "bundle 主干", "file_id",
                    "已采", "目标目录"])
        for i in items:
            w.writerow([i["short"], "P%d" % i["tier"], i["label"], i["region"], i["body"],
                        i["file_id"], "是" if i["stem"] in done else "否",
                        "%s/%s_%s" % (args.chapter, i["short"], i["body"])])
    print("计划 %d 条 → %s" % (len(items), os.path.relpath(p, PATH.ROOT)))
    c = collections.Counter("P%d" % i["tier"] for i in items)
    print("  " + "  ".join("%s=%d" % (k, v) for k, v in sorted(c.items())))
    return 0


def bundle_sizes():
    """{file_id: 解压后总字节}。用 chunks.original_size 累加，≈ bundle 实际大小。"""
    con = sqlite3.connect("file:%s?mode=ro" % ec.CATALOG.replace("\\", "/"), uri=True)
    rows = con.execute(
        "select m.file_id, sum(c.original_size) from chunk_file_map m "
        "join chunks c on c.chunk_id=m.chunk_id group by m.file_id").fetchall()
    con.close()
    return {fid: int(n or 0) for fid, n in rows}


def cmd_export(args):
    """把全集清单落成正式文件（含每场景预估体积），供另一台设备核对进度。"""
    items = scan_catalog(verbose=True)
    done = existing_scenes()
    sizes = bundle_sizes()
    out = args.out or os.path.join(os.path.dirname(ec.IDX_PATH), "场景全集.csv")
    tot = collections.Counter()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["短名", "级别", "标签", "区域", "bundle 主干", "file_id",
                    "预估MB", "已采", "registry键"])
        for i in items:
            mb = sizes.get(i["file_id"], 0) / 1024 / 1024
            tot[i["tier"]] += mb
            w.writerow([i["short"], "P%d" % i["tier"], i["label"], i["region"], i["body"],
                        i["file_id"], "%.1f" % mb,
                        "是" if i["stem"] in done else "否", done.get(i["stem"], "")])
    c = collections.Counter("P%d" % i["tier"] for i in items)
    print("清单 %d 条 → %s" % (len(items), os.path.relpath(out, PATH.ROOT)))
    for t in (1, 2, 3):
        print("  P%d：%3d 个，%.2f GB" % (t, c["P%d" % t], tot[t] / 1024))
    print("  合计：%3d 个，%.2f GB" % (len(items), sum(tot.values()) / 1024))
    return 0


def cmd_run(args):
    bad = ec.preflight(need_adb=True)
    if bad:
        print("前置检查未通过，先修：python collect_all.py --preflight")
        return 1
    items = pick(args)
    if not items:
        print("没有选中任何场景（检查 --tier / --only）")
        return 1

    chapter = args.chapter
    if chapter == PENDING_CHAPTER:
        print("提示：未指定 --chapter，产物落 %s，认图后再改名归档（§20.2 S4）" % chapter)
    os.makedirs(os.path.join(PATH.LIB, chapter), exist_ok=True)

    stages = tuple(s.strip() for s in args.stage.split(",")) if args.stage else STAGES
    print("开始采集 %d 个场景 → %s  阶段=%s  force=%s"
          % (len(items), chapter, ",".join(stages), args.force))
    print("adb 是单设备串行通道，不要开多进程；中断后重跑会自动跳过已完成的。\n")

    t0 = time.time()
    rows, ok = [], 0
    for n, it in enumerate(items, 1):
        print("[%d/%d] %s  (%s)" % (n, len(items), it["short"], it["body"]))
        r = run_one(it, chapter, stages=stages, force=args.force, log=print)
        rows.append(r)
        ok += 1 if r["ok"] else 0
        if n % 10 == 0:
            append_progress(rows)
            rows = []
            el = time.time() - t0
            eta = el / n * (len(items) - n)
            print("  —— 进度 %d/%d，已用 %.0fm，预计还需 %.0fm ——\n"
                  % (n, len(items), el / 60, eta / 60))
    if rows:
        append_progress(rows)

    el = time.time() - t0
    print("\n完成 %d/%d，用时 %.1f 分钟。进度表：%s"
          % (ok, len(items), el / 60, os.path.relpath(PROGRESS, PATH.ROOT)))
    fail = [r for r in read_progress().values()]  # noqa: F841
    print("失败重跑：python collect_all.py --run --only <短名,...> --force")
    return 0 if ok == len(items) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--tier", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--chapter", default=PENDING_CHAPTER)
    ap.add_argument("--stage", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args(argv)

    if args.help or not any([args.preflight, args.list, args.plan, args.export, args.run]):
        print(__doc__)
        return 0
    if args.preflight:
        return cmd_preflight(args)
    if args.list:
        return cmd_list(args)
    if args.export:
        return cmd_export(args)
    if args.plan:
        return cmd_plan(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
