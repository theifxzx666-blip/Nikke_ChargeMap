# 另一台设备采集 · 交付包

把整个仓库拷到另一台电脑，配合一台装了**国际服 NIKKE** 的安卓手机，就能把客户端里
**174 个战斗场景背景**全部采进场景库。

---

## 三步走

### 1 拿到仓库

```bash
git clone https://github.com/theifxzx666-blip/Nikke_ChargeMap.git
cd Nikke_ChargeMap
```

`.gitignore` 已把原始 bundle / 贴图 / glb 挡在外面（它们可重新生成），
但**采集索引（32 MB）是入库的**，clone 完就能直接跑，不需要额外拷文件。

### 2 照 `PROMPT-全量采集.md` 做

这份是完整作业指令，14 节：为什么是扫描式采集、索引版本核对、环境准备、
174 个场景的分级与体积、五条命令、产物结构、章节归属怎么人工归档、
十个坑、验收标准、红线。

### 3 最短路径（想直接开跑就看这个）

```bash
pip install "UnityPy==1.25.4" numpy zstandard Pillow openpyxl pycryptodome

python 工具/采集/collect_all.py --preflight      # 四项检查：catalog / cdb.idx / zstandard / adb
python 工具/采集/collect_all.py --list --tier 1,2 # 看要采什么，已采的会标出来
python 工具/采集/collect_all.py --run --tier 1,2  # 开跑，约 1.5~2 小时
python 工具/paths.py --check                      # 验收
```

---

## 包里有什么

| 文件 | 说明 |
|---|---|
| `PROMPT-全量采集.md` | 完整作业指令（与 `docs/11-安卓全量采集.md` 同内容，离线可用） |
| `../资源库/共享依赖/采集索引/core_catalog.sqlite` | 27 MB，file_id → key → chunk 映射（2026-10-22 快照） |
| `../资源库/共享依赖/采集索引/core_store.cdb.idx` | 4.6 MB，hash → (offset,length) 快照 |
| `../资源库/共享依赖/采集索引/场景全集.csv` | 174 个场景的短名/分级/预估 MB/已采标记 |
| `../工具/采集/collect_all.py` | 全量编排器（枚举/分级/断点续跑/进度表） |
| `../工具/采集/extract_core.py` | 定点提取内核（双块自愈 + adb dd） |
| `../工具/采集/decrypt_nkdb.py` | 手机版本变了时，用 `catalog.ndb` 现解一份 catalog |
| `../工具/采集/dump_tex.py` | 贴图导出（直接落所属场景的 `tex/`） |

**没有放进去的**：`store.cdb`（4.99 GB，别拷，脚本按 offset 定点读）。

---

## 想整包带走（U 盘 / 网盘）

GitHub 已经能拉全，但如果你要走离线，把这几样打进一个压缩包：

```bash
cd Nikke_ChargeMap
zip -r ../地图充能采集包.zip \
  工具/ 资源库/共享依赖/采集索引/ 交付包/ docs/11-安卓全量采集.md \
  PROMPT.md AGENTS.md README.md .gitignore requirements*.txt 2>/dev/null
# 约 35 MB（索引 32 MB + 代码 3 MB）
```

> 不要打整个目录：`资源库/场景库/*/source/`、`*/tex/`、`回收站/` 加起来超过 1 GB，
> 而且都是可重生成或可丢弃的。

---

## 采完怎么合并回主库

见 `PROMPT-全量采集.md` §12：按 `场景全集.csv` 的「已采」列比对，
只搬新场景目录，`registry.json` 用脚本合并（不要直接覆盖，会丢键），
最后重跑 `gen_catalog.py` 与 `paths.py --check`。
