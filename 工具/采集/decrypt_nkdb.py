# -*- coding: utf-8 -*-
"""把设备上的 NKDB（AES-OFB + zlib 分段加密的 SQLite）解密成可查询的 .sqlite。

来源：母体拆包项目 `04_临时车间\\脚本\\tmp_if_decrypt_catalog.py`（解密逻辑未改）。
本项目把它收进采集层，是为了让**另一台设备不必依赖任何外部绝对路径**：
拿自己手机上最新版本的 catalog.ndb 现解一份，就不会因为版本漂移而 hash 全部对不上。

用法：
  python decrypt_nkdb.py <in.ndb> <out.sqlite>

  # 典型：从手机拉原始文件再解
  adb pull /sdcard/Android/data/com.proximabeta.nikke/files/com.shiftup.patch/core/catalog.ndb .
  python decrypt_nkdb.py catalog.ndb 资源库/共享依赖/采集索引/core_catalog.sqlite

NDB 结构（实测 2026-10-22 国际服）：
  NKDB | version(4) | aes_key(16) | segment_size(4) | segment_count(4)
        | offset 表（每段长度 4 或 5 字节，大端）| 各段密文
  IV = struct.pack('<ii', 段序号, 段偏移) + 8 个零字节，AES-OFB，段内 zlib。

注意：**catalog.ndb 必须与 store.cdb 同一版本**。只换其中一个的后果是
「hash 未命中索引」，症状是每个 file_id 都失败，而不是零星几个。
"""
import os
import struct
import sys
import zlib

from Crypto.Cipher import AES


def decrypt_nkdb(input_path, output_path):
    data = open(input_path, "rb").read()
    assert data[:4] == b"NKDB", "not NKDB: %r" % data[:4]
    version = int.from_bytes(data[4:8], "big")
    aes_key = data[8:24]
    segment_size = int.from_bytes(data[24:28], "big")
    segment_count = int.from_bytes(data[28:32], "big")
    print("  version=%d key=%s segsize=%d count=%d"
          % (version, aes_key.hex(), segment_size, segment_count))

    length_byte_count = 5 if segment_size * segment_count > 0xFFFFFFFF else 4
    pos = 32

    def read_offset():
        nonlocal pos
        val = int.from_bytes(data[pos:pos + length_byte_count], "big")
        pos += length_byte_count
        return val

    current_offset = read_offset()
    segments = []
    for i in range(segment_count):
        next_offset = read_offset()
        segments.append((current_offset, next_offset - current_offset, i))
        current_offset = next_offset

    fail = 0
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as out:
        for offset, length, index in segments:
            segment = data[offset:offset + length]
            iv = struct.pack("<ii", index, offset) + b"\x00" * 8
            cipher = AES.new(aes_key, AES.MODE_OFB, iv=iv)
            decrypted = cipher.decrypt(segment)
            try:
                decompressed = zlib.decompress(decrypted)
            except Exception as e:
                fail += 1
                print("  segment %d: zlib fail %s len=%d" % (index, e, len(decrypted)))
                decompressed = decrypted
            out.write(decompressed)
    print("  -> %s (%d bytes)  zlib失败段=%d"
          % (output_path, os.path.getsize(output_path), fail))
    return fail


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        print("用法: python decrypt_nkdb.py <in.ndb> <out.sqlite>")
        sys.exit(2)
    n = decrypt_nkdb(sys.argv[1], sys.argv[2])
    sys.exit(1 if n else 0)
