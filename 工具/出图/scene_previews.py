# -*- coding: utf-8 -*-
"""场景全貌预览图（PROMPT §21.4）：每个战场一张 1920x1080 PNG。

与 5 阵位图（render_views.py）的区别：
  阵位图 = cover_N 原生机位，回答「玩家站这儿看到什么」
  全貌图 = glb 包围盒自动算机位，回答「这张战场整体长什么样」
两者并存，不互相替代。

红线（§20.7 R7）：**纯场景**。点位、序号、HUD 一律不画（dots=0&hud=0&nodata=1）。

用法：
    python 工具/出图/scene_previews.py --all          # 全量，已有则跳过
    python 工具/出图/scene_previews.py 001 cf001     # 指定几个
    python 工具/出图/scene_previews.py --all --force  # 全部重拍
    python 工具/出图/scene_previews.py --check        # 只查缺哪张（不拍）
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from urllib.parse import quote

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
from paths import PATH, ROOT as REPO                        # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
W, H = 1920, 1080
PORT = 8901
MIN_KB = 110                    # 低于此视为纯色/未加载。原来 200 太严：
                                # ocbbg004001 这种大面积纯色天空的远景场景，197KB 就够清晰，会被误判
FOGD = "0.0035"               # 全貌机位留一点空气感：天空球按场景真色渲染后，0 雾会让
                              # 320 m 宽的地面带边缘变成一块悬浮方板（§21.10.1 之后发现）
ELEV = "18"
# 自动曝光（§21.4）：场景本身就横跨「沼泽夜战地面 35/255」到「雪原贴图 200/255」，
# 统一增益必然一边死黑一边过曝。做法是先用 exp=1 探一张，量灰度均值再反算增益重拍。
EXPO_TARGET = 118               # 目标灰度均值
EXPO_OK = (95, 145)             # 已落在区间就不迭代
EXPO_CLAMP = (0.55, 2.3)


def _alive(port):
    s = socket.socket()
    s.settimeout(0.4)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def serve():
    """仓库根起静态服务（fp.html 用 ../../资源库 相对路径，根必须是仓库根）"""
    if _alive(PORT):
        return None
    p = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT),
                          "--bind", "127.0.0.1", "--directory", REPO],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if _alive(PORT):
            return p
        time.sleep(0.25)
    p.terminate()
    raise SystemExit("静态服务起不来（端口 %d）" % PORT)


def render(arena, exp, dst):
    """按指定曝光增益拍一张，返回 (成功, 灰度均值, 方差, KB)"""
    url = ("http://127.0.0.1:%d/%s/viewer/fp.html"
           "?arena=%s&view=overview&w=%d&h=%d&dots=0&hud=0&nodata=1&fogd=%s&elev=%s&exp=%s"
           % (PORT, quote("工具"), arena, W, H, FOGD, ELEV, exp))
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                        "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--window-size=%d,%d" % (W, H), "--virtual-time-budget=15000",
                        "--screenshot=" + dst, url],
                       capture_output=True, text=True, errors="replace")
    if not os.path.exists(dst):
        print("  !! 拍照失败 %-10s %s" % (arena, (r.stderr or "")[-160:]), flush=True)
        return False, 0.0, 0.0, 0
    im = Image.open(dst).convert("RGB")
    if im.size != (W, H):
        im = im.resize((W, H))
        im.save(dst)
    small = im.resize((64, 36)).convert("L")
    b = list(small.get_flattened_data())
    mean = sum(b) / len(b)
    var = sum((x - mean) ** 2 for x in b) / len(b)
    return True, mean, var, os.path.getsize(dst) // 1024


def shoot(arena, force=False):
    dst = PATH.preview(arena)
    if os.path.exists(dst) and not force:
        print("  skip %-10s 已有" % arena, flush=True)
        return True
    tmp = dst.replace(".png", "._tmp.png")
    t0 = time.time()

    # 探针：先按不干预曝光拍一张量灰度
    ok, mean, var, kb = render(arena, 1, tmp)
    if not ok:
        return False
    # var 阈值从 12 降到 4：rf001 是整场景红色调、几乎没有明暗差，方差只有 7.4，但它不是空白
    if kb < MIN_KB or var < 4:
        print("  !! %-10s 疑似空白（%dKB, var=%.1f），保留 %s 待查"
              % (arena, kb, var, os.path.basename(tmp)), flush=True)
        return False

    # 自动曝光：最多迭代 3 轮（大部分场景一轮就落进区间）
    exp = 1.0
    for _ in range(3):
        if EXPO_OK[0] <= mean <= EXPO_OK[1]:
            break
        gain = EXPO_TARGET / max(mean, 1.0)
        exp = min(EXPO_CLAMP[1], max(EXPO_CLAMP[0], exp * gain))
        ok, mean2, var, kb = render(arena, round(exp, 2), tmp)
        if not ok:
            return False
        # 增益是 sRGB 上的近似线性，收敛慢时才用实测比再修一次
        if abs(mean2 - EXPO_TARGET) < 8 or mean2 <= 0:
            mean = mean2
            break
        mean = mean2

    os.replace(tmp, dst)
    print("  ok   %-10s %.1fs exp=%.2f mean=%.0f %dKB var=%.0f"
          % (arena, time.time() - t0, exp, mean, kb, var), flush=True)
    return True


def all_arenas():
    return sorted(PATH.registry().keys())


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    check = "--check" in sys.argv
    arenas = all_arenas() if ("--all" in sys.argv or not args) else args

    if check:
        miss = [a for a in arenas if not os.path.exists(PATH.preview(a))]
        print("预览图 %d/%d，缺 %d：%s" % (len(arenas) - len(miss), len(arenas),
                                          len(miss), " ".join(miss[:12]) or "无"))
        return 1 if miss else 0

    if not os.path.exists(CHROME):
        raise SystemExit("找不到 Chrome：%s" % CHROME)
    PATH.preview_dir()
    srv = serve()
    ok = 0
    t_all = time.time()
    try:
        for a in arenas:
            ok += 1 if shoot(a, force) else 0
    finally:
        if srv:
            srv.terminate()
    print("\n完成 %d/%d 张，%.1f 分钟 → %s"
          % (ok, len(arenas), (time.time() - t_all) / 60.0, PATH.PREVIEWS))
    return 0 if ok == len(arenas) else 2


if __name__ == "__main__":
    raise SystemExit(main())
