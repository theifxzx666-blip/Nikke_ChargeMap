# -*- coding: utf-8 -*-
"""章节目录改名为「H<章号>_<中文名>_<英文名>」（PROMPT §21.1）。

改什么：
  资源库/场景库/<旧>  →  <新>
  分析/<旧>          →  <新>
  registry.json 里该目录下所有场景的 chapter_dir
  场景卡.json   的 chapter_dir（若写了）
  _章节.json    的 chapter_dir / name / name_zh / name_en / name_source
                + 新增 chapter_names（官方章节名，来自 资源库/共享依赖/其他/chapter_names_zh.json）

不改什么：
  场景目录名（S1 不变）、arena 键（S2 不变）、任何数据文件名

译名分三级（§21.1）：
  official  国服 lss 本地化库查到的原文（7 个）
  inherited 仓库既有且已核验（3 个）
  translit  直译，待核（其余）

用法：
  python 工具/采集/rename_chapters.py --dry     # 只打印对照表
  python 工具/采集/rename_chapters.py           # 实际改名
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from paths import PATH, LIB, ANA                             # noqa: E402

# region → (中文名, 来源)。依据逐条写在 PROMPT §21.1 的表里，不在这里重复论证。
NAME = {
    "cityforest":               ("城市林地", "inherited"),
    "iceland":                  ("雪原", "official"),
    "wasteland":                ("荒地", "translit"),
    "desert":                   ("沙漠", "official"),
    "greathole":                ("巨洞", "translit"),
    "arkcity":                  ("方舟城", "translit"),
    "desertcrystal":            ("沙漠结晶", "translit"),
    "cityforestundercrystal":   ("晶化城市森林", "inherited"),
    "swamplandjungle":          ("沼泽丛林", "inherited"),
    "motherwhalefield":         ("母鲸领域", "inherited"),
    "whitearkcity":             ("白色方舟城", "official"),
    "arkcityday":               ("方舟城白昼", "translit"),
    "cityforestunder":          ("城市林地下层", "translit"),
    "cityforestunderelevator":  ("城市林地电梯", "translit"),
    "arkout":                   ("方舟城外", "translit"),
    "ebg002_001":               ("特殊布景002", "translit"),
    "gravedigger":              ("掘墓", "official"),
    "lostsector":               ("迷失地区", "official"),
    "ocean":                    ("海洋", "translit"),
    "redocean":                 ("赤红海洋", "translit"),
    "redoceanfarsea":           ("赤红海洋远海", "translit"),
    "simulation":               ("模拟室", "official"),
    "surface":                  ("地表", "translit"),
    "tower":                    ("无限之塔", "official"),
    "volcano":                  ("火山", "translit"),
}

CHAP_NAMES = os.path.join(PATH.SHARED, "其他", "chapter_names_zh.json")


def chapter_names():
    if not os.path.exists(CHAP_NAMES):
        return {}
    d = json.load(open(CHAP_NAMES, encoding="utf-8"))
    return d.get("names") or {}


def new_name(meta):
    """按 §21.1 算目录名。region 缺失就直接抛，不猜。"""
    region = meta.get("region")
    if not region:
        raise SystemExit("_章节.json 缺 region：%r" % meta.get("chapter_dir"))
    zh, src = NAME.get(region, (region, "translit"))
    disp = meta.get("display")
    if disp is None:
        return "N_%s_%s" % (zh, region), zh, src
    return "H%02d_%s_%s" % (int(disp), zh, region), zh, src


def plan():
    """[(旧, 新, 中文, 来源, meta)]"""
    out = []
    for d in sorted(os.listdir(LIB)):
        p = os.path.join(LIB, d, "_章节.json")
        if not os.path.isdir(os.path.join(LIB, d)) or not os.path.exists(p):
            continue
        meta = json.load(open(p, encoding="utf-8"))
        if d == meta.get("chapter_dir") and "name_en" in meta and "name_zh" in meta:
            nn, zh, src = new_name(meta)
            if nn == d:
                continue                                  # 已合规
        nn, zh, src = new_name(meta)
        out.append((d, nn, zh, src, meta))
    return out


def patch_card(meta, newdir, zh, src, names):
    meta["chapter_dir"] = newdir
    meta["name_zh"] = zh
    meta["name_en"] = meta["region"]
    meta["name_source"] = src
    meta["name"] = zh                                  # 兼容旧字段
    chs = meta.get("chapters") or []
    if chs:
        got = {str(c): names.get("%02d" % c) for c in chs if names.get("%02d" % c)}
        if got:
            meta["chapter_names"] = got
            meta["chapter_name_key"] = "Locale_Stage:chapter_name_%02d" % chs[0]
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    names = chapter_names()
    todo = plan()
    if not todo:
        print("0 条待改：目录名已全部符合 §21.1")
        return 0

    print("%-32s → %-40s %-12s %s" % ("旧目录", "新目录", "中文名", "来源"))
    for old, new, zh, src, meta in todo:
        print("%-32s → %-40s %-12s %s" % (old, new, zh, src))
    print("\n共 %d 个目录" % len(todo))
    if a.dry:
        return 0

    reg_p = os.path.join(LIB, "registry.json")
    reg = json.load(open(reg_p, encoding="utf-8"))
    for old, new, zh, src, meta in todo:
        src_dir = os.path.join(LIB, old)
        dst_dir = os.path.join(LIB, new)
        if os.path.exists(dst_dir):
            raise SystemExit("目标已存在，拒绝覆盖：%s" % dst_dir)
        os.rename(src_dir, dst_dir)
        ana_old, ana_new = os.path.join(ANA, old), os.path.join(ANA, new)
        if os.path.isdir(ana_old):
            os.rename(ana_old, ana_new)
        # registry
        for k, v in reg["scenes"].items():
            if v.get("chapter_dir") == old:
                v["chapter_dir"] = new
        # 章节卡
        cp = os.path.join(dst_dir, "_章节.json")
        m = patch_card(json.load(open(cp, encoding="utf-8")), new, zh, src, names)
        json.dump(m, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        # 场景卡
        for sc in m.get("scenes") or []:
            v = reg["scenes"].get(sc)
            if not v:
                continue
            sp = os.path.join(dst_dir, v["dir"], "场景卡.json")
            if not os.path.exists(sp):
                continue
            card = json.load(open(sp, encoding="utf-8"))
            if card.get("chapter_dir") != new:
                card["chapter_dir"] = new
                json.dump(card, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    json.dump(reg, open(reg_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n完成：目录、registry、场景卡、章节卡已同步。接着跑 工具/校验/gen_catalog.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
