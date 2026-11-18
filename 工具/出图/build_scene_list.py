# -*- coding: utf-8 -*-
"""生成查看器用的单文件场景清单（PROMPT §21.12）。

查看器（`工具/viewer/app.html`）跑在浏览器里，不能像 Python 那样到处 os.listdir，
所以把「章节目录 / 中文名 / 英文名 / glb 路径 / 5 个掩体位机位 / 天空索引」一次性
烘进 `资源库/共享依赖/scene_list.json`，前端只拉这一个文件。

数据来源（全部实测，不猜）：
  registry.json           场景 → chapter_dir / dir
  <chapter_dir>/_章节.json  章号、中文名、英文名、章名表
  共享依赖/skybox_index.json 天空贴图文件名与三段色
  <dir>/mesh/slots.json      cover_1..5 的 camera_position（世界坐标，[[x,y,z]] 多一层）

用法：
    python 工具/出图/build_scene_list.py
    python 工具/出图/build_scene_list.py --check    # 只校验，不写盘
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from paths import PATH, LIB, ROOT                            # noqa: E402

OUT = os.path.join(ROOT, "资源库", "共享依赖", "scene_list.json")
SKYIDX = os.path.join(ROOT, "资源库", "共享依赖", "skybox_index.json")
COVERS = ["cover_1", "cover_2", "cover_3", "cover_4", "cover_5"]


def flat(v):
    """slots.json 里的坐标是 [[x,y,z]]（多套一层数组），统一拆成 [x,y,z]"""
    if isinstance(v, list) and v and isinstance(v[0], list):
        return v[0]
    return v


def chapter_meta(cdir):
    p = os.path.join(LIB, cdir, "_章节.json")
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def main():
    check = "--check" in sys.argv
    reg = PATH.registry()
    sky = json.load(open(SKYIDX, encoding="utf-8")) if os.path.exists(SKYIDX) else {}

    groups = {}
    miss_cov, miss_sky, miss_glb = [], [], []

    for arena in sorted(reg, key=lambda a: (a[0].isdigit() is False, a)):
        r = reg[arena]
        cdir, d = r["chapter_dir"], r["dir"]
        if cdir not in groups:
            m = chapter_meta(cdir)
            groups[cdir] = {
                "chapter_dir": cdir,
                "chapter": m.get("display"),
                "chapter_id": m.get("chapter_id"),
                "chapters": m.get("chapters") or ([m["display"]] if m.get("display") else []),
                "chapter_names": m.get("chapter_names") or {},
                "name_zh": m.get("name_zh") or m.get("name") or cdir,
                "name_en": m.get("name_en") or m.get("region") or cdir,
                "scenes": [],
            }

        glb = "mesh/arena_%s.glb" % arena
        if not os.path.exists(os.path.join(LIB, cdir, d, glb)):
            miss_glb.append(arena)

        # ---- 5 个掩体位：camera_position 是场景世界坐标（各场景同模板，实测）----
        covers = {}
        sp = os.path.join(LIB, cdir, d, "mesh", "slots.json")
        if os.path.exists(sp):
            try:
                slots = json.load(open(sp, encoding="utf-8")).get(arena) or {}
                for k in COVERS:
                    c = flat((slots.get(k) or {}).get("camera_position"))
                    if c:
                        covers[k] = [round(float(x), 4) for x in c]
            except Exception:
                pass
        if len(covers) < 5:
            miss_cov.append(arena)

        sk = sky.get(arena)
        if not sk:
            miss_sky.append(arena)

        cnt = 0
        mp = os.path.join(LIB, cdir, d, "mesh", "slots.json")
        groups[cdir]["scenes"].append({
            "arena": arena,
            "dir": "%s/%s" % (cdir, d),
            "glb": glb,
            "covers": covers,
            "sky": {"file": (sk or {}).get("file") or (sk or {}).get("side"),
                    "tone": (sk or {}).get("tone")},
        })

    gl = list(groups.values())
    # 主线章节按章号升序，非主线（N_*）排最后。
    # 注意：`N_城市林地` 的 display 是 0 而不是 None，用 `not chapter` 一起判 --
    # 旧写法只判 None，结果 0 被当成「第 0 章」排到最前面（查看器首屏就是它）。
    gl.sort(key=lambda g: (not g["chapter"], g["chapter"] or 0, g["chapter_dir"]))

    doc = {
        "generated": "2026-10-28",
        "source": "registry.json + _章节.json + skybox_index.json + slots.json",
        "base": "../../资源库/场景库/",
        "covers": COVERS,
        "total": sum(len(g["scenes"]) for g in gl),
        "groups": gl,
    }

    print("章节组 %d · 场景 %d" % (len(gl), doc["total"]))
    print("缺 5 掩体位: %d %s" % (len(miss_cov), " ".join(miss_cov[:8])))
    print("缺天空索引: %d %s" % (len(miss_sky), " ".join(miss_sky[:8])))
    print("缺 glb    : %d %s" % (len(miss_glb), " ".join(miss_glb[:8])))

    if check:
        bad = miss_cov or miss_sky or miss_glb
        print("检查%s" % ("失败" if bad else "通过"))
        return 1 if bad else 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(doc, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写入 %s  %dKB" % (OUT, os.path.getsize(OUT) // 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
