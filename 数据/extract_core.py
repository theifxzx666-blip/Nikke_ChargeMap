# -*- coding: utf-8 -*-
"""从安卓国际服 core/chunk/store.cdb 定点提取指定 bundle。

链路：core_catalog.sqlite -> store.cdb.idx -> adb dd -> zstd -> 按 file_offset 拼接
注意：chunk hash 命中索引 #M 时真实数据块常在 #M+1（双块规则），
      这里用 (original_size) 做校验，在 M-1/M/M+1 中自愈选取。
"""
import sqlite3, struct, subprocess, sys, os

CATALOG = r"F:\Codex\Nikke\Nikke_Skills\拆包\04_临时车间\国际服采集_20261022\catalog\core_catalog.sqlite"
IDX_PATH = r"F:\Codex\Nikke\Nikke_Skills\地图充能计算\_work\core_store.cdb.idx"
STORE = "/sdcard/Android/data/com.proximabeta.nikke/files/com.shiftup.patch/core/chunk/store.cdb"

import zstandard as zstd
DCTX = zstd.ZstdDecompressor()

_IDX_LIST = None
_IDX_POS = None

def load_idx():
    global _IDX_LIST, _IDX_POS
    d = open(IDX_PATH, "rb").read()
    lst, pos = [], {}
    for i in range(len(d) // 28):
        rec = d[i*28:(i+1)*28]
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
        data = data[:length]   # dd 统计行混入尾部
    return data

def fetch_chunk(h, olen, debug=None):
    """按 hash 定位并解压，返回恰好 olen 字节的原始数据"""
    m = _IDX_POS.get(bytes(h))
    if m is None:
        raise RuntimeError("hash 未命中索引")
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
    open(out_path, "wb").write(bytes(buf))
    return len(buf), dbg

if __name__ == "__main__":
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
