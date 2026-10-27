# -*- coding: utf-8 -*-
"""从安卓客户端 core/chunk/store.cdb 定点提取指定 bundle。

链路：core_catalog.sqlite -> store.cdb.idx -> adb dd -> zstd -> 按 file_offset 拼接

三个坑（都踩过，脚本已内置处理）：
  1. 双块偏移：chunk hash 命中索引第 #M 条时，真实数据块常在 #M+1。
     症状是解压成功但长度不符、相邻文件长度互相「错位交换」。
     解法：以 original_size 校验，在 M-1 / M / M+1 中自愈选取。
  2. dd 统计行混入 stdout：即使 exec-out，读长仍多出数十字节。
     解法：按已知长度截断。
  3. Git Bash 路径转换：/sdcard/... 会被改写成 Windows 路径。
     解法：调用方在命令前加 MSYS_NO_PATHCONV=1（本脚本内部用 list 传参，不受影响）。

路径（v15 起不再硬编码，见 docs/11-安卓全量采集.md §2）：
  默认  INDEXES/核心索引/core_catalog.sqlite + core_store.cdb.idx
  覆盖   环境变量 NIKKE_CATALOG / NIKKE_CDB_IDX / NIKKE_STORE
  也可在 import 后直接改本模块的 CATALOG / IDX_PATH / STORE
"""
import os
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(HERE))

try:
    from paths import PATH                                   # noqa: E402
    IDX_DIR = os.path.join(PATH.RES, "共享依赖", "采集索引")
except Exception:                                            # 允许脱离 paths 单独运行
    PATH = None
    IDX_DIR = os.path.join(ROOT, "资源库", "共享依赖", "采集索引")

CATALOG = os.environ.get("NIKKE_CATALOG") or os.path.join(IDX_DIR, "core_catalog.sqlite")
IDX_PATH = os.environ.get("NIKKE_CDB_IDX") or os.path.join(IDX_DIR, "core_store.cdb.idx")
STORE = os.environ.get("NIKKE_STORE") or (
    "/sdcard/Android/data/com.proximabeta.nikke/files/com.shiftup.patch/core/chunk/store.cdb")

try:
    import zstandard as zstd
    DCTX = zstd.ZstdDecompressor()
except ImportError:                                          # 只用 catalog 列清单时不需要
    DCTX = None

_IDX_LIST = None
_IDX_POS = None


# ── 前置检查：新设备上最高频的两种失败，给结论而不是堆栈 ────────────────
def preflight(need_adb=True, quiet=False):
    """返回 [(项, 是否通过, 说明)]，全通过返回空列表。"""
    bad = []

    if not os.path.exists(CATALOG):
        bad.append(("catalog", False,
                    "缺少 %s\n     修复：用 decrypt_nkdb.py 解一份，或从旧机拷过来" % CATALOG))
    if not os.path.exists(IDX_PATH):
        bad.append(("cdb.idx", False,
                    "缺少 %s\n     修复：adb pull 手机上同版本 store.cdb.idx，或跑 工具/采集/pull_index.py"
                    % IDX_PATH))
    if DCTX is None:
        bad.append(("zstandard", False, "未安装：pip install zstandard"))

    if need_adb:
        if not shutil.which("adb"):
            bad.append(("adb", False, "adb 不在 PATH（装 scrcpy 自带，winget install Genymobile.scrcpy）"))
        else:
            r = subprocess.run(["adb", "devices"], capture_output=True, text=True)
            online = [l.split("\t")[0] for l in r.stdout.splitlines()[1:]
                      if "\tdevice" in l]
            if not online:
                bad.append(("adb", False,
                            "没有已授权的设备。开 USB 调试 → 手机上点「允许」→ adb devices 应显示 device"))

    if not quiet:
        for name, ok, msg in bad:
            print("  !! %-10s %s" % (name, msg))
        if not bad:
            print("  前置检查通过：catalog / cdb.idx / zstandard / adb 就绪")
    return bad


def load_idx(path=None):
    """把 4.7 MB 的 store.cdb.idx 读成 (list[(off,len)], dict[hash -> index])。"""
    global _IDX_LIST, _IDX_POS
    p = path or IDX_PATH
    d = open(p, "rb").read()
    lst, pos = [], {}
    for i in range(len(d) // 28):
        rec = d[i * 28:(i + 1) * 28]
        ent = (struct.unpack("<Q", rec[0:8])[0], struct.unpack("<I", rec[8:12])[0])
        lst.append(ent)
        pos.setdefault(rec[12:28], i)
    _IDX_LIST, _IDX_POS = lst, pos
    return lst, pos


def adb_read(off, length):
    cmd = ["adb", "exec-out", "dd", "if=" + STORE, "bs=4096",
           "skip=%d" % off, "count=%d" % length, "iflag=skip_bytes,count_bytes"]
    r = subprocess.run(cmd, capture_output=True)
    data = r.stdout
    if len(data) > length:
        data = data[:length]          # dd 统计行混入尾部
    return data


def fetch_chunk(h, olen, debug=None):
    """按 hash 定位并解压，返回恰好 olen 字节的原始数据"""
    if _IDX_POS is None:
        load_idx()
    m = _IDX_POS.get(bytes(h))
    if m is None:
        raise RuntimeError("hash 未命中索引（多半是 catalog 与 store.cdb 版本不一致）")
    for delta in (0, 1, -1):
        i = m + delta
        if not (0 <= i < len(_IDX_LIST)):
            continue
        off, ln = _IDX_LIST[i]
        if ln <= 0:
            continue
        raw = adb_read(off, ln)
        if len(raw) != ln:
            continue
        try:
            dec = DCTX.decompress(raw, max_output_size=olen)
        except Exception:
            continue
        if len(dec) == olen:
            if debug is not None:
                debug.append("idx#%d(delta=%+d)" % (i, delta))
            return dec
    raise RuntimeError("chunk 解压校验失败 hash=%s olen=%d" % (bytes(h).hex()[:16], olen))


def extract(file_id, out_path, con):
    rows = list(con.execute(
        "select c.chunk_id, c.hash, c.compressed_size, c.original_size, m.file_offset "
        "from chunk_file_map m join chunks c on c.chunk_id=m.chunk_id "
        "where m.file_id=? order by m.file_offset", (file_id,)))
    if not rows:
        raise RuntimeError("file_id=%d 无 chunk" % file_id)
    buf = bytearray()
    dbg = []
    for cid, h, clen, olen, foff in rows:
        buf += fetch_chunk(h, olen, dbg)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    open(out_path, "wb").write(bytes(buf))
    return len(buf), dbg


if __name__ == "__main__":
    import sqlite3
    if len(sys.argv) < 3 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("用法: python extract_core.py <输出目录> \"<key LIKE 模式>\" [更多模式…]")
        print("例：  python extract_core.py ./out \"%spotbackground(hd)%\"")
        sys.exit(0)
    bad = preflight()
    if bad:
        sys.exit(1)
    con = sqlite3.connect(CATALOG)
    load_idx()
    outdir = sys.argv[1]
    os.makedirs(outdir, exist_ok=True)
    for pat in sys.argv[2:]:
        for fid, key in con.execute(
                "select file_id, key from files_chunktype where key like ? order by file_id", (pat,)):
            name = os.path.basename(key)
            path = os.path.join(outdir, name)
            try:
                n, dbg = extract(fid, path, con)
                head = open(path, "rb").read(6)
                print("OK  %-7d %-9d %-6s %s" % (fid, n, head.decode("ascii", "replace"), name[:72]))
            except Exception as e:
                print("ERR %-7d %s  %s" % (fid, e, name[:60]))
    con.close()
