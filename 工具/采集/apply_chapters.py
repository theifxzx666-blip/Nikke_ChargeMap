# -*- coding: utf-8 -*-
"""按章节归档场景：把 H00_待归档 里的场景移到对应的章节目录。

判据（不靠猜，全部来自包内表）：
  CampaignChapterTable.records[].chapter  = 显示章号（`id` 只是主键，别用，错一章就是这么来的）
  CampaignChapterTable.records[].field_id = fcbg_<区域>_<NNN>，取出区域名
  区域名对齐 bundle 侧 `sbg_<区域>_<NNN>`：多数同名，个别要过 ALIAS（见下）

两级落位：
  区域在章节表里出现 → H<该区域最小章号>_<名称>，并在 _章节.json 的 `chapters` 记全部共用章号
  区域不在章节表里   → N_<区域>（塔/模拟/活动/EX 类，本就不是主线章节）

已知不可解：`stage → 具体哪张 sbg` 客户端没有表（CampaignStageTable 只有服务端下发的
spot_id，campaignlevelmapgroup 只有 _stageId + 坐标，见 docs/06 §1 末段）。所以归档粒度是
「该区域/该章的战场全集」，不是「3-7 关用第几张图」。

用法：
  python apply_chapters.py --dry     # 只看会怎么搬
  python apply_chapters.py           # 实际搬（搬完跑 工具/校验/gen_catalog.py）
"""
import argparse
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from paths import PATH                                        # noqa: E402

PENDING = "H00_待归档"

# 章节表的 field_id 前缀与 bundle 区域名不同名的情况（逐条实证，不靠猜）
#   chapter_id 35 / chapter 34 / field_id fcbg_cityforestcrystal_007
#   ⇄ bundle 侧 sbg_cityforestundercrystal_001~005（docs/06 §1 表）
ALIAS = {"cityforestcrystal": "cityforestundercrystal"}

# boss/布景类 bundle 的区域名带后缀（swamplandjunglebbg008 → swamplandjunglebbg → swamplandjungle），
# 它们与主战场同属该章：docs/06 §1「sbg_swamplandjungle_001~005（常规）+ swamplandjunglebbg008/009（boss）」
VAR_SUFFIX = ("bbg", "mbg", "ebg", "bmf", "cabal", "xbg", "xba", "eba", "bba")

# 中文名与来源统一走 rename_chapters.NAME（§21.1 单一表），这里不再另立一份
from rename_chapters import NAME, chapter_names                  # noqa: E402


def chapter_regions():
    """{区域: [显示章号, ...]}，章号 = records[].chapter。"""
    p = PATH.shared("CampaignChapterTable.json")
    recs = (json.load(open(p, encoding="utf-8")).get("records") or [])
    out = {}
    for r in recs:
        f = r.get("field_id") or ""
        if not f.startswith("fcbg_"):
            continue
        reg = f.split("_")[1]
        reg = ALIAS.get(reg, reg)
        out.setdefault(reg, []).append(r["chapter"])
    for v in out.values():
        v.sort()
    return out


def normalize(region, table):
    """把 boss/布景变体的区域名折回主战场区域；折不动就原样返回。"""
    if region in table:
        return region
    for suf in VAR_SUFFIX:
        if region.endswith(suf) and region[:-len(suf)] in table:
            return region[:-len(suf)]
    return region


def target(region, table):
    """§21.1 目录形态：H<章号>_<中文名>_<英文名> / N_<中文名>_<英文名>（中文在前）"""
    from rename_chapters import NAME                        # 单一译名来源，不另立一份表
    base = normalize(region, table)
    zh = NAME.get(base, (base,))[0]
    chs = table.get(base) or []
    if chs:
        return "H%02d_%s_%s" % (chs[0], zh, base), chs
    return "N_%s_%s" % (zh, base), []


def _save(obj, path):
    PATH.write_json(obj, path)


def write_chapter_meta(chapter_dir):
    """_章节.json 由该目录下已登记的场景反推，只补不删（人工核验字段保留）。"""
    a = [s for s, v in PATH.registry().items() if v["chapter_dir"] == chapter_dir]
    if not a:
        return
    p = os.path.join(PATH.LIB, chapter_dir, "_章节.json")
    meta = {}
    if os.path.exists(p):
        meta = json.load(open(p, encoding="utf-8"))
    region = PATH.registry()[a[0]]["region"]
    table = chapter_regions()
    chs = table.get(normalize(region, table)) or []
    meta.setdefault("region", region)
    zh, src = NAME.get(region, (region, "translit"))
    meta["name"] = zh
    meta.setdefault("name_zh", zh)
    meta.setdefault("name_en", region)
    meta.setdefault("name_source", src)
    meta["chapters"] = chs
    if chs:
        names = chapter_names()
        got = {str(c): names.get("%02d" % c) for c in chs if names.get("%02d" % c)}
        if got:
            meta.setdefault("chapter_names", got)
            meta.setdefault("chapter_name_key", "Locale_Stage:chapter_name_%02d" % chs[0])
    if not chs:
        meta.setdefault("note", "章节表无此区域的 field_id：属塔/模拟/活动/EX 类或主线变体待核；"
                                "确认后补 chapters 并改名 H<章号>_<名>")
    meta["chapter_dir"] = chapter_dir
    m = re.match(r"H(\d+)_", chapter_dir)
    if m and "display" not in meta:
        # 目录名里的章号就是显示章号（= CampaignChapterTable.chapter，不是 id）
        meta["display"] = int(m.group(1))
        meta["chapter_id"] = meta["display"] + 1
        meta["display_source"] = "目录名 H<chapter>"
    meta["scenes"] = sorted(a)
    meta.setdefault("evidence", "CampaignChapterTable.chapter + field_id → 区域；"
                                "区域级归档，非关卡级")
    meta.setdefault("verified", None)
    _save(meta, p)

    # 场景卡里的 chapter 段：gen_catalog 的「章节」列取这里，缺了就显示 None
    display = int(m.group(1)) if m else 0
    for k in a:
        cp = os.path.join(PATH.scene_dir(k), "场景卡.json")
        if not os.path.exists(cp):
            continue
        card = json.load(open(cp, encoding="utf-8"))
        card["chapter"] = {"display": display,
                           "chapter_id": (meta.get("chapter_id", display + 1) if m else 0)}
        _save(card, cp)


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("-h", "--help", action="store_true")
    args = ap.parse_args()
    if args.help:
        print(__doc__)
        return 0

    table = chapter_regions()
    reg = PATH.registry()
    moves = []
    for short, v in sorted(reg.items()):
        tgt, chs = target(v["region"], table)
        cur = v["chapter_dir"]
        # 已人工核验的章节目录（H34_晶化城市森林 那种）不搬不改名，只补 chapters
        if cur.startswith("H") and cur != PENDING:
            keep_region = (PATH.chapter_meta(cur) or {}).get("region")
            if keep_region and keep_region == normalize(v["region"], table) and tgt.startswith("H"):
                continue
        if cur != tgt:
            moves.append((short, cur, tgt, chs))

    print("场景 %d 个，需移动 %d 个" % (len(reg), len(moves)))
    for short, old, new, chs in moves:
        print("  %-12s %-22s → %-34s %s" % (short, old, new,
                                            ("第 %s 章" % ",".join(map(str, chs))) if chs else "非主线"))

    if args.dry:
        print("\n--dry：未改动任何文件")
        return 0

    done = 0
    for short, old, new, _chs in moves:
        sd = os.path.join(PATH.LIB, old, reg[short]["dir"])
        dd = os.path.join(PATH.LIB, new, reg[short]["dir"])
        if not os.path.isdir(sd):
            print("  !! %s 源目录不存在：%s" % (short, sd))
            continue
        os.makedirs(os.path.dirname(dd), exist_ok=True)
        if os.path.isdir(dd):
            print("  !! %s 目标已存在，跳过：%s" % (short, dd))
            continue
        shutil.move(sd, dd)                       # 同盘 move，不产生拷贝
        reg[short]["chapter_dir"] = new
        PATH.write_json({"scenes": reg}, os.path.join(PATH.LIB, "registry.json"))
        PATH._reg = None                          # 清缓存，否则下面读的还是旧 dict
        card_p = os.path.join(dd, "场景卡.json")
        if os.path.exists(card_p):
            c = json.load(open(card_p, encoding="utf-8"))
            c["chapter_dir"] = new
            _save(c, card_p)
        done += 1

    for d in sorted({n for _s, _o, n, _c in moves} | {v["chapter_dir"] for v in reg.values()}):
        write_chapter_meta(d)

    # 待归档目录空了就删掉它的 _章节.json，避免留空壳
    pd = os.path.join(PATH.LIB, PENDING)
    if os.path.isdir(pd) and not [x for x in os.listdir(pd) if x != "_章节.json"]:
        for f in os.listdir(pd):
            os.remove(os.path.join(pd, f))
        os.rmdir(pd)

    print("\n已移动 %d 个。下一步：python 工具/校验/gen_catalog.py && python 工具/paths.py --check"
          % done)
    return 0


if __name__ == "__main__":
    sys.exit(main())
