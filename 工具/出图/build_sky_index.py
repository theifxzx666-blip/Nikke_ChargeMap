# -*- coding: utf-8 -*-
"""天空索引（PROMPT §21.11）：把每个场景的 skybox 贴图名固化下来，供 viewer 直接查。

为什么要这个文件：fp.html 是前端，拿不到目录列表，只能靠 `sbg_<REGION>_skybox_side.png`
拼文件名去试。但 `REGION` 只来自 registry / slots，而 slots.json **没有 region 字段**，
出纯场景图（nodata=1）时 REGION 一律回落成 `swamplandjungle` ——
结果 112 个场景里只有 7 个能命中自己的天空，其余 105 个加载失败、天空退化成一块纯灰背景
（gd001 上半屏全灰就是这个）。改成拆包时扫一遍目录、把真实文件名写进索引，就不再靠猜。

三种命名都见过（实测 112 场景）：
  108 个  sbg_<X>_skybox_side / _upper / _under.png     ← 常态
    3 个  sbg_<X>_skybox2_side / _upper / _under.png    ← 换皮变体
    1 个  sbg_<X>_skybox.png                            ← 单张（gd001，巨洞，本来就是黑的）

产物：资源库/共享依赖/skybox_index.json
    { "001": {"kind": "3piece", "prefix": "sbg_swamplandjungle_skybox",
              "side": "...", "upper": "...", "under": "..."},
      "gd001": {"kind": "single", "file": "sbg_gravembg002_skybox.png"}, ... }

用法：
    python 工具/出图/build_sky_index.py
    python 工具/出图/build_sky_index.py --check
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from paths import PATH, LIB                                  # noqa: E402

OUT = os.path.join(os.path.dirname(LIB), "共享依赖", "skybox_index.json")


def _tone(path):
    """取天空贴图的三段颜色：天顶 / 地平线 / 天底（0~1 sRGB）。

    为什么需要：viewer 原来把 `scene.background` 和雾色都写死成 0.4627 中性灰，
    于是所有场景（雪原、荒漠、巨洞、水下）头顶都压着同一层灰、远景板也统一被灰雾抹平，
    硬边特别扎眼。改成把场景自己天空的颜色喂给雾和背景，远景板就能被「同色雾」自然吃掉。
    """
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB").resize((64, 64), Image.LANCZOS)
    except Exception:
        return None
    px = list(im.getdata())

    def band(y0, y1):
        v = [p for y in range(y0, y1) for p in px[y * 64:(y + 1) * 64]]
        n = len(v) or 1
        return [round(sum(p[i] for p in v) / n / 255.0, 4) for i in range(3)]

    return {"top": band(0, 10), "mid": band(28, 36), "bot": band(54, 64)}


def scan(texdir):
    """返回该场景的天空描述；没有天空贴图返回 None"""
    if not os.path.isdir(texdir):
        return None
    fs = [f for f in os.listdir(texdir) if "skybox" in f.lower() and f.lower().endswith(".png")]
    if not fs:
        return None
    # 三件套：取前缀（去掉 _side/_upper/_under）
    tri = {}
    for f in fs:
        m = re.match(r"^(.+_skybox2?)_(side|upper|under)\.png$", f, re.I)
        if m:
            tri.setdefault(m.group(1), {})[m.group(2).lower()] = f
    for pre, d in tri.items():
        if "side" in d:                       # side 是必需品，缺 upper/under 也能铺个球
            rec = {"kind": "3piece", "prefix": pre,
                   "side": d.get("side"), "upper": d.get("upper"), "under": d.get("under")}
            rec["tone"] = _tone(os.path.join(texdir, d["side"]))
            return rec
    # 单张
    rec = {"kind": "single", "file": sorted(fs)[0]}
    rec["tone"] = _tone(os.path.join(texdir, rec["file"]))
    return rec


def build(verbose=True):
    reg = PATH.registry()
    out, miss = {}, []
    for arena in sorted(reg):
        r = reg[arena]
        td = os.path.join(LIB, r["chapter_dir"], r["dir"], "tex")
        d = scan(td)
        if d:
            out[arena] = d
        else:
            miss.append(arena)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
    if verbose:
        kinds = {}
        for v in out.values():
            kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
        print("天空索引 → %s" % OUT)
        print("  场景 %d · 已登记 %d · 无天空 %d" % (len(reg), len(out), len(miss)))
        for k, v in sorted(kinds.items()):
            print("  %-8s %d" % (k, v))
        if miss:
            print("  无天空：%s" % " ".join(miss[:20]))
    return out, miss


def check():
    if not os.path.exists(OUT):
        print("!! 缺 %s，先跑 build_sky_index.py" % OUT)
        return 1
    j = json.load(open(OUT, encoding="utf-8"))
    reg = PATH.registry()
    bad = [a for a in reg if a not in j]
    gone = []
    for a, d in j.items():
        if a not in reg:
            continue
        r = reg[a]
        td = os.path.join(LIB, r["chapter_dir"], r["dir"], "tex")
        for k in ("side", "upper", "under", "file"):
            if d.get(k) and not os.path.exists(os.path.join(td, d[k])):
                gone.append("%s/%s" % (a, d[k]))
    print("天空索引 %d 场景 · 未登记 %d · 文件丢失 %d" % (len(j), len(bad), len(gone)))
    for x in gone[:10]:
        print("  丢 %s" % x)
    return 0 if not bad and not gone else 1


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check())
    build()
