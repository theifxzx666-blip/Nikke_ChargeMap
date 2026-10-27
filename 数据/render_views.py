# -*- coding: utf-8 -*-
"""按阵位出图：每个战场 × 5 个阵位各拍一张，转 WebP。

页面上「换掩体」要同时换图和换点位表，所以 5 个阵位各要一张。
PNG 单张 1.6MB，7×5=35 张要 56MB；转 WebP q88 约 120KB，总量 ~4MB。

前提：本地 8899 端口有静态服务（glTF 需要 http 才能加载）：
    python -m http.server 8899 --bind 127.0.0.1      # 在 数据/ 目录下

用法：
    python render_views.py                    # 7 张战场 × 5 阵位
    python render_views.py 001 bbg009         # 指定战场
    python render_views.py --views=cover_3    # 只拍某一阵位
    python render_views.py --force            # 已有图也重拍
"""
import os
import subprocess
import sys
import time

from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "render")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
SWAMP = ["001", "002", "003", "004", "005", "bbg008", "bbg009"]
VIEWS = ["cover_1", "cover_2", "cover_3", "cover_4", "cover_5"]
W, H = 1600, 900
QUALITY = 88


def shoot(arena, view, force=False):
    dst_webp = os.path.join(OUT, "fp_%s_%s.webp" % (arena, view))
    if os.path.exists(dst_webp) and not force:
        print("  skip %s %s（已有）" % (arena, view), flush=True)
        return True
    tmp = os.path.join(OUT, "_tmp_%s_%s.png" % (arena, view))
    # dots=0：不画点位 sprite（标注改由页面 HTML 叠加层负责，才能随筛选重绘）
    # hud=0 ：不画底部数据条和标题（否则图里烧死一份旧的点位数）
    url = ("http://127.0.0.1:8899/viewer/fp.html?arena=%s&view=%s&w=%d&h=%d&dots=0&hud=0&nodata=1"
           % (arena, view, W, H))
    t0 = time.time()
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                        "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--window-size=%d,%d" % (W, H), "--virtual-time-budget=12000",
                        "--screenshot=" + tmp, url],
                       capture_output=True, text=True, errors="replace")
    if not os.path.exists(tmp):
        print("  !! 拍照失败 %s %s  %s" % (arena, view, (r.stderr or "")[-200:]), flush=True)
        return False
    # 等页面把 glb 和贴图都加载完再截图，首帧可能是空的：检查非纯色像素占比
    im = Image.open(tmp).convert("RGB")
    if im.size != (W, H):
        im = im.resize((W, H))
    # 近乎纯色 = 相机没定位 / glb 没加载。别静默产出灰图让页面看起来"没变化"。
    # 正常 1600x900 PNG 约 1.6MB，纯灰只有 10~20KB。
    png_kb = os.path.getsize(tmp) // 1024
    if png_kb < 200:
        print("  !! %s %s 截图只有 %dKB，疑似空白（相机/glb 没加载），保留 %s 待查"
              % (arena, view, png_kb, os.path.basename(tmp)), flush=True)
        return False
    im.save(dst_webp, quality=QUALITY, method=6)
    os.remove(tmp)
    kb = os.path.getsize(dst_webp) // 1024
    print("  ok   %s %s  %.1fs  %dKB" % (arena, view, time.time() - t0, kb), flush=True)
    return True


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    views = VIEWS
    force = "--force" in sys.argv
    for a in sys.argv[1:]:
        if a.startswith("--views="):
            views = a.split("=")[1].split(",")
    arenas = args or SWAMP
    if not os.path.exists(CHROME):
        raise SystemExit("找不到 Chrome：%s" % CHROME)
    os.makedirs(OUT, exist_ok=True)
    n = 0
    t_all = time.time()
    for a in arenas:
        for v in views:
            n += shoot(a, v, force) and 1 or 0
    print("\n完成 %d/%d 张，%.1f 分钟"
          % (n, len(arenas) * len(views), (time.time() - t_all) / 60.0))


if __name__ == "__main__":
    main()
