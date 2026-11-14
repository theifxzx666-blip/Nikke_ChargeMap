# -*- coding: utf-8 -*-
"""实预图（PROMPT §21.10）：**游戏原生机位**下的纯场景图 —— 玩家在游戏里真正看到的画面。

与「预览/」的区别：
  预览/    = bbox 自动算的俯瞰全貌，回答「这张战场整体长什么样」
  实预图/  = slots.json 里的 cover_N.camera_position 原始机位（角色身后 4.5m / 视高 2.34m /
             FOV 60°，均为 spotcameracontrol 实证值），回答「玩家进图看到什么」

红线：
  **完全还原游戏内** —— 不加 ov 滤镜、不调曝光（不传 exp）、不关雾（不传 fogd，用默认 0.006）。
  这不是「好看的图」，是「和游戏里一模一样的图」，任何增益都会让它失真。
  点位/序号/HUD/遮罩一律不画（dots=0&hud=0&nodata=1）。

用法：
    python 工具/出图/scene_reel.py                      # 112 场景 × cover_3（进图位置）
    python 工具/出图/scene_reel.py --views=all          # 112 场景 × cover_1..5（560 张）
    python 工具/出图/scene_reel.py 001 cf001 --force
    python 工具/出图/scene_reel.py --check
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from urllib.parse import quote

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from paths import PATH, ROOT as REPO, view                  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE_H = 1080                 # 纵向固定 1080，宽度由画幅反推（§21.13）
AR = 16 / 9                   # 画幅：16:9 / 21:9
PORT = 8903
MIN_KB = 200
# 相机参数只认 工具/参数真源.json —— 显式带进 URL，避免依赖页面默认值
with open(os.path.join(REPO, "工具", "参数真源.json"), encoding="utf-8") as _f:
    FOV = float(json.load(_f)["camera"]["fov_vertical_deg"])
# --port=N：多进程并行出图时各占一个端口（单张约 70s，112 张串行要 2 小时）
for _a in sys.argv[1:]:
    if _a.startswith("--port="):
        PORT = int(_a.split("=", 1)[1])


def size():
    return int(round(BASE_H * AR)), BASE_H


def cam_pose():
    """从唯一数据源 camera_params.json 取机位姿态，**显式传参**给 fp.html。

    2026-10-28 教训（§25.1）：此前依赖 fp.html 的默认值，而默认值还留着被否掉的
    prefab 偏航 −38.6°，对照实验证明了正确值却忘了落地，导致 112 张全量返工。
    所以出图脚本必须自己传，不许吃页面默认值。

    俯角返回 **字符串**：pitch_mode=auto 时传 "auto"，由 fp.html 按逐场景几何反解；
    取常数会让 ocebg001001（相机 6.322m）这种例外失去自适应性。
    """
    p = os.path.join(REPO, "资源库", "共享依赖", "引擎件", "camera_params.json")
    try:
        d = json.load(open(p, encoding="utf-8"))["参数"]["推导"]
        yaw = float(d["chosen_yaw_deg"])
        foot = float(d.get("foot_screen_y", 0.87))
        if str(d.get("pitch_mode", "")).lower() == "auto":
            return yaw, "auto", foot
        return yaw, "%g" % float(d["chosen_pitch_deg"]), foot
    except Exception:
        return 0.0, "auto", 0.87     # 兜底：仍走 auto，避免又退回已被证伪的常数

def _alive(port):
    s = socket.socket()
    s.settimeout(0.4)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def serve():
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


def shoot(arena, v, force=False):
    W, H = size()
    dst = PATH.reel(arena, v, AR)
    if os.path.exists(dst) and not force:
        print("  skip %-10s %-9s 已有" % (arena, v), flush=True)
        return True
    tmp = dst.replace(".png", "._tmp.png")
    # 注意：故意不传 exp / fogd / view=overview / dist / dy —— 走 fp.html 的游戏原生分支与默认雾
    # ar 只影响画幅（横向扩视野），纵向 FOV 仍是 60°，所以它不算「改变画面」
    # yaw/pitch 必须显式传：吃页面默认值出过一次全量返工的事故（§25.1）
    # pitch=auto + foot 走逐场景反解，不能写死角度（§26）
    yaw, pitch, foot = cam_pose()
    url = ("http://127.0.0.1:%d/%s/viewer/fp.html"
           "?arena=%s&view=%s&w=%d&h=%d&ar=%.4f&fov=%g&dots=0&hud=0&nodata=1"
           "&yaw=%g&pitch=%s&foot=%g"
           % (PORT, quote("工具"), arena, v, W, H, AR, FOV, yaw, pitch, foot))
    t0 = time.time()
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                        "--enable-unsafe-swiftshader", "--hide-scrollbars",
                        "--window-size=%d,%d" % (W, H), "--virtual-time-budget=15000",
                        "--screenshot=" + tmp, url],
                       capture_output=True, text=True, errors="replace")
    if not os.path.exists(tmp):
        print("  !! 拍照失败 %-10s %-9s %s" % (arena, v, (r.stderr or "")[-160:]), flush=True)
        return False
    im = Image.open(tmp).convert("RGB")
    if im.size != (W, H):
        im = im.resize((W, H))
        im.save(tmp)
    small = im.resize((64, 36)).convert("L")
    b = list(small.get_flattened_data())
    mean = sum(b) / len(b)
    var = sum((x - mean) ** 2 for x in b) / len(b)
    kb = os.path.getsize(tmp) // 1024
    if kb < MIN_KB or var < 12:
        print("  !! %-10s %-9s 疑似空白（%dKB, var=%.1f），保留 %s 待查"
              % (arena, v, kb, var, os.path.basename(tmp)), flush=True)
        return False
    os.replace(tmp, dst)
    print("  ok   %-10s %-9s %.1fs %dKB mean=%.0f"
          % (arena, v, time.time() - t0, kb, mean), flush=True)
    return True


def main():
    global AR
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    check = "--check" in sys.argv
    vs = ["cover_3"]
    for a in sys.argv[1:]:
        if a.startswith("--views="):
            k = a.split("=", 1)[1]
            vs = [view(x) for x in (PATH.views(args[0]) if k == "all" and args else
                                    (range(1, 6) if k == "all" else k.split(",")))]
        elif a.startswith("--ar="):
            k = a.split("=", 1)[1].strip()
            AR = {"16:9": 16 / 9, "169": 16 / 9, "21:9": 21 / 9, "219": 21 / 9}.get(k)
            if AR is None:
                AR = float(k)
                if AR <= 1:
                    raise SystemExit("画幅必须是宽高比（如 21:9 或 2.3333）")
    arenas = args or sorted(PATH.registry().keys())

    if check:
        miss = [(a, v) for a in arenas for v in vs if not os.path.exists(PATH.reel(a, v, AR))]
        print("实预图 %d/%d，缺 %d" % (len(arenas) * len(vs) - len(miss), len(arenas) * len(vs), len(miss)))
        return 1 if miss else 0

    if not os.path.exists(CHROME):
        raise SystemExit("找不到 Chrome：%s" % CHROME)
    PATH.reel_dir(AR)
    srv = serve()
    ok = 0
    t_all = time.time()
    try:
        for a in arenas:
            for v in vs:
                ok += 1 if shoot(a, v, force) else 0
    finally:
        if srv:
            srv.terminate()
    total = len(arenas) * len(vs)
    print("\n完成 %d/%d 张（%d×%d，%.3f:1），%.1f 分钟 → %s"
          % (ok, total, size()[0], size()[1], AR, (time.time() - t_all) / 60.0, PATH.reel_dir(AR)))
    return 0 if ok == total else 2


if __name__ == "__main__":
    raise SystemExit(main())
