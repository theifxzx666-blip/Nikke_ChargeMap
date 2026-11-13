# -*- coding: utf-8 -*-
"""全览图（PROMPT §21.5）：把 112 张场景预览拼成可索引的大图。

契约（§21.5）：全览图内**只放纯场景图，不画任何充能点位**；带点位的图属「充能图」，另存一区。
换言之 —— 全览图 = 无点位场景的索引版；充能图 = 带点位的实战版。两者不混。

排版（2026-10-28 重做，起因：6 列 × 520 缩略图看不清内容）
  3 列 × 960 宽缩略图（原图 1920 的一半），行内三行字
  按章节目录分组，组不被卷切断
  单卷高度 ≤ MAXH，超出自动分卷

产物：
  正式产物/场景图/全览图/全览图_<n>.png
  正式产物/场景图/全览图/全览图.md      ← 索引：第几卷、第几行第几列是哪张

用法：
    python 工具/出图/contact_sheet.py
    python 工具/出图/contact_sheet.py --cols 2 --thumb 1280 --maxh 7000
"""
from __future__ import annotations

import json
import os
import sys
import time

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from paths import PATH, LIB                                  # noqa: E402

OUTDIR = os.path.join(PATH.SHOTS, "全览图")
COLS = 3
THUMB_W = 960                    # 缩略图宽（原图 1920 的 50%，细节可辨）
CELL_PAD = 14
TEXT_H = 88
MAXH = 6800
BG = (16, 22, 20)
FG = (232, 240, 235)
MUT = (150, 168, 158)
ACC = (120, 210, 170)
HEAD = (255, 208, 120)
HEADBG = (34, 46, 40)

FONT_CANDS = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
              r"C:\Windows\Fonts\simhei.ttf"]


def font(sz, bold=False):
    for p in (FONT_CANDS[1], FONT_CANDS[0], FONT_CANDS[2]) if bold else FONT_CANDS:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                continue
    return ImageFont.load_default()


def groups():
    """[(chapter_dir, 中文名, 英文名, display, chapters, [arena...])]，H 按章号在前，N 在后"""
    reg = PATH.registry()
    g = {}
    for arena, v in reg.items():
        g.setdefault(v["chapter_dir"], []).append(arena)
    out = []
    for d in g:
        p = os.path.join(LIB, d, "_章节.json")
        meta = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
        out.append((d, meta.get("name_zh") or meta.get("name") or d,
                    meta.get("name_en") or meta.get("region") or "",
                    meta.get("display"), meta.get("chapters") or [], sorted(g[d])))
    out.sort(key=lambda x: (x[3] is None, x[3] if x[3] is not None else 0, x[0]))
    return out


def _head_text(d, zh, en, chs, n):
    """组标题：H00 是多章共用，不能写「第 0 章」"""
    if not chs:
        lead = "非主线"
    elif len(chs) == 1:
        lead = "第 %d 章" % chs[0]
    elif len(chs) <= 4:
        lead = "第 %s 章共用" % "/".join(str(c) for c in chs)
    else:
        lead = "第 %d~%d 章共用（%d 章）" % (min(chs), max(chs), len(chs))
    return "%s   %s · %d 场景" % (lead, d, n)


def layout(gs, cols, cell_h, maxh):
    """把组切成卷：[(卷号, [(kind, payload)...])]，kind = head/cell"""
    vols, cur, h = [], [], 0
    for d, zh, en, ch, chs, arenas in gs:
        rows = (len(arenas) + cols - 1) // cols
        need = 46 + rows * cell_h + 16
        if cur and h + need > maxh:
            vols.append(cur)
            cur, h = [], 0
        cur.append(("head", (d, zh, en, ch, chs, len(arenas))))
        h += 46
        for i, a in enumerate(arenas):
            cur.append(("cell", (a, i)))
        h += rows * cell_h + 16
    if cur:
        vols.append(cur)
    return vols


def main():
    cols, thumb_w, maxh = COLS, THUMB_W, MAXH
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--cols":
            cols = int(argv[i + 1]); i += 2
        elif argv[i] == "--thumb":
            thumb_w = int(argv[i + 1]); i += 2
        elif argv[i] == "--maxh":
            maxh = int(argv[i + 1]); i += 2
        else:
            i += 1
    thumb_h = int(thumb_w * 9 / 16)
    cell_w, cell_h = thumb_w + CELL_PAD * 2, thumb_h + TEXT_H + CELL_PAD * 2
    W = cols * cell_w + CELL_PAD
    TITLE_H = int(76 * (thumb_w / 960.0))      # 卷首大标题区：字 38px + 下留白，62 仍会贴边
    HEAD_H = 52                                 # 章节头色条（27px 字 + 上下留白）
    os.makedirs(OUTDIR, exist_ok=True)

    # 字号随缩略图尺寸缩放，保证在任何 --thumb 下文字都不糊
    k = thumb_w / 960.0
    f_title = font(int(38 * k), True)
    f_head = font(int(27 * k), True)
    f_a = font(int(23 * k), True)
    f_zh = font(int(21 * k))
    f_en = font(int(18 * k))
    name_dx = int(112 * k)          # 中文名的横向偏移（arena 短名宽度）

    gs = groups()
    vols = layout(gs, cols, cell_h, maxh)
    reg = PATH.registry()
    index = ["# 全览图索引", "",
             "由 `工具/出图/contact_sheet.py` 生成，**不要手改**。",
             "每格 %d×%d 缩略图（原图 1920×1080 的 %d%%），单卷最高 %d px。"
             % (thumb_w, thumb_h, round(thumb_w / 19.2), maxh),
             "", "> 全览图内只有纯场景，**不含充能点位**；带点位的图见 `正式产物/场景图/充能图/`。", ""]
    made = []

    for vi, items in enumerate(vols, 1):
        # 每卷先分回「组」：[(组头, [arena...])]，绘制与算高都按组走
        blocks = []
        for kind, pay in items:
            if kind == "head":
                blocks.append([pay, []])
            else:
                blocks[-1][1].append(pay[0])
        H = TITLE_H + CELL_PAD
        for _, arenas in blocks:
            H += HEAD_H + ((len(arenas) + cols - 1) // cols) * cell_h + 16
        H += CELL_PAD
        im = Image.new("RGB", (W, H), BG)
        dr = ImageDraw.Draw(im)
        ncell = sum(len(a) for _, a in blocks)
        dr.text((CELL_PAD + 4, int(TITLE_H * 0.28)),
                "NIKKE 场景全览 · 第 %d/%d 卷 · %d 场景 · %s"
                % (vi, len(vols), ncell, time.strftime("%Y-%m-%d")),
                font=f_title, fill=ACC)
        index += ["## 全览图_%d.png" % vi, "",
                  "| 章节 | 行 | 列 | arena | 中文名 | 英文名 |", "|---|---|---|---|---|---|"]
        y = TITLE_H
        for (d, zh_g, en_g, ch, chs, n), arenas in blocks:
            t = _head_text(d, zh_g, en_g, chs, n)
            dr.rectangle([CELL_PAD, y, W - CELL_PAD, y + HEAD_H - 10], fill=HEADBG)
            dr.text((CELL_PAD + 14, y + 8), t, font=f_head, fill=HEAD)
            y += HEAD_H
            for i, a in enumerate(arenas):
                col, row = i % cols, i // cols
                cx = CELL_PAD + col * cell_w
                cy = y + row * cell_h
                pv = PATH.preview(a)
                tx, ty0 = cx + CELL_PAD, cy + CELL_PAD
                if os.path.exists(pv):
                    im.paste(Image.open(pv).convert("RGB").resize((thumb_w, thumb_h), Image.LANCZOS),
                             (tx, ty0))
                else:
                    dr.rectangle([tx, ty0, tx + thumb_w, ty0 + thumb_h],
                                 outline=(150, 70, 70), width=2)
                    dr.text((tx + 12, ty0 + 12), "缺预览图", font=f_zh, fill=(220, 120, 120))
                r = reg.get(a, {})
                zh = en = ""
                try:
                    meta = json.load(open(os.path.join(LIB, r["chapter_dir"], "_章节.json"),
                                         encoding="utf-8"))
                    zh, en = meta.get("name_zh", ""), meta.get("name_en", "")
                except Exception:
                    pass
                ty = ty0 + thumb_h + int(9 * k)
                dr.text((tx, ty), a, font=f_a, fill=ACC)
                dr.text((tx + name_dx, ty + 2), zh, font=f_zh, fill=FG)
                dr.text((tx, ty + int(34 * k)), en, font=f_en, fill=MUT)
                index.append("| %s | %d | %d | `%s` | %s | %s |"
                             % (d, row + 1, col + 1, a, zh, en))
            y += ((len(arenas) + cols - 1) // cols) * cell_h + 16
        outp = os.path.join(OUTDIR, "全览图_%d.png" % vi)
        im.save(outp)
        made.append(outp)
        print("  ok 全览图_%d.png  %dx%d  %dKB"
              % (vi, W, H, os.path.getsize(outp) // 1024), flush=True)
        index.append("")

    with open(os.path.join(OUTDIR, "全览图.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(index))
    print("\n%d 卷 → %s" % (len(made), OUTDIR))


if __name__ == "__main__":
    main()
