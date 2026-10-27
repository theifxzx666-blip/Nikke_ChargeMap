# -*- coding: utf-8 -*-
"""按阵位批量重算：7 张 35 章战场 × 5 个阵位（cover_1~5），**组间并行**。

每个阵位跑完整链路（组内必须串行）：
    scan_px  →  verify_px  →  audit_px  →  sim_charge
顺序不能乱：verify_px 会整份重写 px_*.json，sim_charge 的轮换结果写在它的
verify.field_sim 里，跑到 verify 前面会被冲掉。

串行 35 组约 87 分钟；12 核上开 6 路并行约 15 分钟。组内仍是串行，互不干扰
（每个阵位读写自己的 px_<arena>_<view>.json / audit_<arena>_<view>.json）。

断点续跑：px_<a>_<v>.json 里已有 verify.field_sim 且 audit 文件在 → 跳过。

用法：
    python batch_views.py                    # 35 章全部，默认 6 路
    python batch_views.py --jobs=8           # 加宽
    python batch_views.py 001 bbg009         # 指定战场
    python batch_views.py --views=cover_3    # 只跑某个阵位
    python batch_views.py --force            # 忽略断点，全部重跑
"""
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

PY = sys.executable
SWAMP = ["001", "002", "003", "004", "005", "bbg008", "bbg009"]
VIEWS = ["cover_1", "cover_2", "cover_3", "cover_4", "cover_5"]
LOCK = threading.Lock()


def say(msg):
    with LOCK:
        print(msg, flush=True)
        with open("_batch_views.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")


def done(a, v):
    """该阵位是否已跑完整条链（scan+verify+audit+sim）。"""
    px = os.path.join("导出", "px_%s_%s.json" % (a, v))
    au = os.path.join("导出", "audit_%s_%s.json" % (a, v))
    if not (os.path.exists(px) and os.path.exists(au)):
        return False
    try:
        d = json.load(open(px, encoding="utf-8"))
    except Exception:
        return False
    return bool((d.get("verify") or {}).get("field_sim"))


def run(args):
    t0 = time.time()
    r = subprocess.run([PY] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    dt = time.time() - t0
    out = (r.stdout or "").strip().splitlines()
    head = out[0] if out else "(no output)"
    err = (r.stderr or "").strip().splitlines()
    if r.returncode != 0:
        head = "!! FAIL rc=%d  %s" % (r.returncode, (err[-1] if err else head))
    say("%-50s %6.1fs  %s" % (" ".join(args), dt, head))
    return r.returncode == 0


def job(spec):
    idx, total, a, v, force = spec
    if not force and done(a, v):
        say("[%d/%d] %s %s  已完成，跳过" % (idx, total, a, v))
        return (a, v, True, True)
    say("\n[%d/%d] %s %s  开始" % (idx, total, a, v))
    ok = run(["scan_px.py", a, "--view=" + v])
    ok &= run(["verify_px.py", a, "--view=" + v, "--sim=300"])
    ok &= run(["audit_px.py", a, "--view=" + v])
    ok &= run(["sim_charge.py", a, "--view=" + v])
    say("[%d/%d] %s %s  %s" % (idx, total, a, v, "OK" if ok else "FAIL"))
    return (a, v, ok, False)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    views, jobs, force = VIEWS, 6, False
    for a in sys.argv[1:]:
        if a.startswith("--views="):
            views = a.split("=")[1].split(",")
        if a.startswith("--jobs="):
            jobs = max(1, int(a.split("=")[1]))
        if a == "--force":
            force = True
    arenas = args or SWAMP

    plan = [(i, len(arenas) * len(views), a, v, force)
            for i, (a, v) in enumerate([(a, v) for a in arenas for v in views], 1)]
    say("\n==== %s  %d 组 / %d 路并行  %s ===="
        % (time.strftime("%Y-%m-%d %H:%M"), len(plan), jobs,
           "强制重跑" if force else "断点续跑"))
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        res = list(ex.map(job, plan))
    fails = [(a, v) for a, v, ok, _ in res if not ok]
    skip = sum(1 for *_, s in res if s)
    say("\n全部完成 %.1f 分钟（跳过 %d，失败 %d %s）"
        % ((time.time() - t0) / 60.0, skip, len(fails), fails))


if __name__ == "__main__":
    main()
