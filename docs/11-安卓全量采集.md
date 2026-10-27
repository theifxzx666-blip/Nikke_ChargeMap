# 11 · 在另一台设备上做全量战场采集

> 这篇是**给另一台电脑（或另一台电脑上的 AI 助手）的作业指令**。
> 目标：只凭「GitHub 上的这个仓库」+「一台装了国际服 NIKKE 的安卓手机」，
> 把客户端里**全部战斗场景背景**采进场景库，跑完装配，供后续点位分析使用。
>
> 写完时间：2026-10-27 ｜ 对应仓库提交：v15 ｜ 实测基准机：Windows + Python 3.13 + UnityPy 1.25.4

---

## 0 一句话

**本机已有的 16 个场景不用重采；另一台机器从 0 开始，跑 `collect_all.py` 一条命令把剩下 158 个扫进 `资源库/场景库/`。**

---

## 1 为什么是「扫描式采集」而不是「按章节采」

先说清一个**已验证的硬约束**，否则会走错方向：

| 想拿的东西 | 客户端里有没有 | 结论 |
|---|---|---|
| 第 N 章用哪张背景 | **没有** | `CampaignStageTable` 只有服务端下发的 `spot_id`；`campaignlevelmapgroup` 只有 `_stageId` + 坐标；270 个 `LDtkLevelFile` 的 `internal_id` 是另一套 hash 域，`entry_data` 为空 |
| 有哪些战斗背景 | **有**，全集 174 个 | `catalog.sqlite` 里 `spotbackground(hd)_assets_sbg_*.bundle` |

所以**无法**「按章节点名采集」。正确做法是**把全集扫下来**，章节归属事后人工认图归档
（做法见 §7）。这也是为什么本工具叫 `collect_all` 而不叫 `collect_chapter`。

---

## 2 采集索引：仓库里有一份，但**优先用你自己手机的**

采集链路是「catalog 查 file_id → cdb.idx 查 hash → adb dd 定点读 → zstd 解压」。
两个索引必须与手机上的 `store.cdb` **同一版本**：

| 文件 | 体积 | 仓库里的位置 | 说明 |
|---|---:|---|---|
| `core_catalog.sqlite` | 27 MB | `资源库/共享依赖/采集索引/` | 快照日期 **2026-10-22**（国际服） |
| `core_store.cdb.idx` | 4.6 MB | `资源库/共享依赖/采集索引/` | 同上，169426 条 `off(8)+len(4)+hash(16)` |

**版本漂移的判定与处理**（这是新设备最容易踩的一步）：

```
症状：每个 file_id 都报「hash 未命中索引」或「chunk 解压校验失败」
      —— 注意是"每个"，不是零星几个。零星失败是双块偏移，脚本已自愈；全失败就是版本不一致。
处理：1) 从手机上取同版本的两个文件覆盖（下面三条命令）
      2) 若 catalog.ndb 也变了，用 decrypt_nkdb.py 现解一份
```

```bash
# ① 设备路径（国际服 packge = com.proximabeta.nikke；国服是 com.tencent.nikke）
CORE=/sdcard/Android/data/com.proximabeta.nikke/files/com.shiftup.patch/core

# ② 取索引（注意 MSYS_NO_PATHCONV=1，否则 Git Bash 会把 /sdcard 改写成 Windows 路径）
MSYS_NO_PATHCONV=1 adb pull $CORE/chunk/store.cdb.idx  资源库/共享依赖/采集索引/core_store.cdb.idx

# ③ 取加密 catalog 并解密成 sqlite
MSYS_NO_PATHCONV=1 adb pull $CORE/catalog.ndb  临时车间/catalog.ndb
python 工具/采集/decrypt_nkdb.py 临时车间/catalog.ndb 资源库/共享依赖/采集索引/core_catalog.sqlite
```

> `store.cdb` 本身 **4.99 GB，不要 pull**。脚本只按 offset 定点读需要的块。

---

## 3 环境准备

```bash
# 依赖（版本是实测可用的组合，UnityPy 跨大版本 API 变过，别乱升）
pip install "UnityPy==1.25.4" numpy zstandard Pillow openpyxl pycryptodome

# 期望
python -c "import UnityPy,numpy,zstandard,PIL,openpyxl;print('ok')"
python -c "import Crypto;print('ok')"      # decrypt_nkdb 需要，包名 pycryptodome

# adb（scrcpy 自带）
winget install Genymobile.scrcpy
adb devices      # 必须看到 <序列号>  device；unauthorized 表示手机上没点"允许"
```

手机侧：开发者选项 → USB 调试 → 插线 → 手机上点「允许」。
**用原装线**：`adb dd` 每秒要读几十块，线材差会频繁断连（症状是零星 `dd` 返回空）。

---

## 4 采集范围与体积（实测 catalog 全集）

| 级别 | 数量 | 预估体积 | 内容 | 建议 |
|---|---:|---:|---|---|
| **P1 主战场** | 96 | 0.79 GB | `sbg_<区域>_<NNN>`，主线战斗真正用的背景 | **必采** |
| **P2 boss/布景** | 16 | 0.10 GB | `bbg / mbg / ebg / cabal`（如 `swamplandjunglebbg008` 圣甲虫） | **必采** |
| **P3 变体** | 62 | 0.45 GB | `_rightclear / _midclear / _sky / _b / _oc / custom / fly / xba / eba …` | 可后补 |
| 合计 | **174** | **1.34 GB** | 其中 16 个本仓库已采 | — |

P3 多为同场景的清除/天空/特殊位变体，点位通常与主场景共享，**先跳过不影响主线结论**。

数字来源：`python 工具/采集/collect_all.py --export`（每次 catalog 变了要重跑这条）。

---

## 5 五条命令

```bash
# 0) 前置检查：catalog / cdb.idx / zstandard / adb 四项，缺什么直说
python 工具/采集/collect_all.py --preflight

# 1) 看全集与已采状态
python 工具/采集/collect_all.py --list --tier 1,2

# 2) 清单落盘（含每场景预估 MB、已采标记）→ 资源库/共享依赖/采集索引/场景全集.csv
python 工具/采集/collect_all.py --export

# 3) 正式采集（P1+P2，adb 单设备串行，别开并行）
python 工具/采集/collect_all.py --run --tier 1,2

# 4) 验收
python 工具/paths.py --check
python 工具/校验/gen_catalog.py --check
```

**单场景内部链路**（`--run` 自动串起来，每步失败只记错不中断整批）：

| # | 阶段 | 命令/函数 | 落位 |
|---|---|---|---|
| 1 | extract | `extract_core.extract` | `<场景>/source/<stem>.bundle`（登记 `sha1_16`） |
| 2 | card | 写场景卡 | `<场景>/场景卡.json` |
| 3 | registry | 登记 | `资源库/场景库/registry.json`（此后 `PATH.*` 才认这个场景） |
| 4 | assembly | `工具/还原/build_assembly.py` | `<场景>/mesh/assembly_<短名>.json` |
| 5 | tex | `工具/采集/dump_tex.py` | `<场景>/tex/*.png` + `index.json` |
| 6 | glb | `工具/还原/export_glb.py` | `<场景>/mesh/arena_<短名>.glb` |
| 7 | slots | `build_slots.build` | `<场景>/mesh/slots.json` |
| 8 | recard | 回填 `tris/props/hitbox/covers/tex.count` | 场景卡 `status → 已还原` |

**断点续跑**：看 `mesh/assembly_<短名>.json` 在不在，在就跳过；`--force` 才重跑。
**只补某一阶段**：`--stage tex --only gh001,gh002`。
**只跑几个**：`--only sj001,gh002`。
**进度表**：`分析/_采集进度.csv`（每 10 个 flush 一次，含耗时/错误摘要）。

耗时参考：单场景 `extract` 约 40~60 s（9 MB ≈ 280 个 chunk，每个一次 `adb dd`），
其余 7 步合计约 8 s（实测基准机 7.9 s）。**P1+P2 的 98 个待采 ≈ 1.5~2 小时**；
全量 158 个 ≈ 2.5~3 小时。`adb` 是单设备串行通道，**开多进程只会互相拖慢**。

---

## 6 产物长什么样

```
资源库/场景库/
├── registry.json                      ← 短名 → 目录的真源（未登记 = 场景不存在）
├── H00_待归档/                         ← 未指定章节时落这里
│   ├── _章节.json
│   └── gh001_greathole_001/
│       ├── 场景卡.json                 ← 含 source 段 sha1_16、mesh 统计、status
│       ├── source/sbg_greathole_001.bundle
│       ├── mesh/{assembly_gh001.json, arena_gh001.glb, arena_gh001_meta.json, slots.json}
│       └── tex/*.png + index.json
└── H35_沼泽丛林/ …                     ← 已归档的 3 章 16 场景
```

**短名规则**（`collect_all.short_name()`）：`<区域缩写><变体><3位编号>`，
如 `arkcity_001 → ac001`、`swamplandjunglebbg008 → sjbbg008`、`cityforest_sky_001a → cfsky001a`。
区域缩写表在脚本顶部 `REGION_ABBR`，**新增区域要加一条**，否则会退化成前两字母。
短名必须全局唯一 —— 冲突时脚本自动加 `_2` 后缀，但**出现过就说明缩写表该补了**。

---

## 7 章节归属：唯一需要人工的一步

采集完的产物落在 `H00_待归档/`，因为客户端给不出「第 N 章用哪张图」。归档办法：

1. **认图**：打开 `工具/viewer/index.html?arena=<短名>`（需先 `启动战场查看器.bat`），
   或直接看 `tex/` 里的天空盒与大件贴图；
2. **对表**：`资源库/共享依赖/CampaignChapterTable.json` 给出章节显示号与章节目录名（`chapter` 字段才是章号，`id` 是主键 —— 别用错，35 章那次的教训见 `docs/06`）；
3. **改名**：把场景目录从 `H00_待归档/` 移到 `H<章号>_<中文名>/`，同步改三处：
   - `场景卡.json` 的 `chapter_dir` 与 `chapter{display,chapter_id}`
   - `registry.json` 对应条目的 `chapter_dir`
   - 目标章节的 `_章节.json` 的 `scenes` 列表
4. **验一遍**：`python 工具/paths.py --check`（改名不对会立刻报 `UnknownScene` 或路径不存在）

> 认不准就不归档。留在 `H00_待归档/` 也能被工具读到（只要 registry 登记了），
> 只是清单里章号显示 0。

---

## 8 采完之后跑点位（可选，但这是项目的真正目的）

采集只到「几何 + 贴图 + 阵位」为止。要出充能点：

```bash
# 单场景四阶段：scan → verify → audit → rotate，约 5~30 s
python 工具/分析/analyze.py gh001 --view 3

# 全阵位 + 并行（点位分析不碰 adb，可以开并发）
python 工具/分析/analyze.py gh001 --views 1,2,3,4,5 --jobs 4

# 批量：先把 batch 清单喂进去（未登记的场景不会参与，见 §20.2 S9）
python 工具/分析/analyze.py --list
```

`analyze.py` 会写 `分析/<章节>/<短名>/_run_cover_N.json`，含**几何指纹**
（`tris/props/bytes`）。几何改了没重算，`--schema` 会报出来 —— 这是防
「2026-10-27 那次 `z=zmin` 修复后下游没重跑」同类事故的闸门，别绕过。

---

## 9 验收标准

| 项 | 通过条件 | 命令 |
|---|---|---|
| 索引可用 | 前置四项全绿 | `--preflight` |
| 场景件齐 | `--check` 返回 0（`待补` 不计失败） | `python 工具/paths.py --check` |
| 表单闸门 | 通过（提示可忽略） | `python 工具/校验/gen_catalog.py --check` |
| 装配非空 | 每场景 `tris > 0`，且 `tris/顶点比 ≥ 1.5` | 看 `--list` 或场景卡 |
| 阵位 | `covers == 5`（少数场景只有部分） | 场景卡 `mesh.covers` |
| 贴图 | `tex.count > 0`，`index.json` 存在 | 场景卡 `tex.count` |
| 重复采集 | 重跑 `--run` 应全部 `跳过`，不产生新文件 | `--run --tier 1` 再跑一次 |

`tris/顶点比 < 1.5` 是要警惕的信号：实测全取 1.88、只取一层 0.91。
低说明踩了 `z=zmin` 侧壁过滤（三角形只剩 24.5%），详见 `docs/04-跨章节对照.md` §3。

---

## 10 十个坑（都踩过，按出现频率排序）

| # | 症状 | 根因 | 处理 |
|---|---|---|---|
| 1 | 每个 file_id 都「hash 未命中」 | catalog 与 `store.cdb` 版本不一致 | §2 重新取索引；只换一半没用 |
| 2 | 零星「chunk 解压校验失败」 | 双块偏移：hash 命中 `#M` 时真实块常在 `#M+1` | 脚本已自愈（M-1/M/M+1 按 `original_size` 校验），不用管 |
| 3 | `adb dd` 返回少几十字节 | `exec-out` 仍混入 dd 统计行 | 脚本按已知长度截断，不用管 |
| 4 | `/sdcard/...` 被改写成 `E:/...` | Git Bash 路径转换 | 命令前加 `MSYS_NO_PATHCONV=1` |
| 5 | `UnknownScene: 未在 registry.json 登记` | 新采集的场景还没登记就去调 `PATH.*` | `collect_all` 的顺序已保证先登记；手写脚本要照 §5 表第 3 步 |
| 6 | 贴图全丢、glb 里一片白 | `dump_tex` 没跑就跑了 `export_glb`（glb 从 `tex/` 取图） | 顺序不能变：assembly → **tex** → glb |
| 7 | `--check` 报「source/ 为空」但在别的机器上是好的 | `source/` 是 gitignore 的，新克隆必然为空 | 只当提示；场景卡 `source` 段有 `sha1_16` 就说明采过 |
| 8 | `adb` 跑到一半断 | USB 线材/供电，或手机锁屏 | 关锁屏、用原装线；断点续跑重来即可 |
| 9 | 采完 `tris` 明显偏小 | 该版本 mesh 压缩格式变了 | 先和 `--export` 里的预估 MB 比：bundle 正常但 tris 小，去查 `build_assembly.parse` 的压缩网格分支 |
| 10 | 短名撞了（出现 `_2` 后缀） | `REGION_ABBR` 缺该区域 | 补一条缩写，删掉冲突产物重跑 |

---

## 11 红线（继承 PROMPT §20，不许破）

| # | 红线 |
|---|---|
| R5 | 不许自己拼路径，一律走 `工具/paths.py` |
| R6 | 采集/分析结果不许写回 `资源库/场景库/*/source/`（那是原件） |
| R8 | 三张表单必须 `gen_catalog.py` 生成，不许手写 |
| R9 | 未在 `registry.json` 登记的场景不参与批量 |
| R11 | **`store.cdb` 不许整份 pull**（4.99 GB），只走定点读 |
| R12 | 不许改成并行 `adb`；串行是唯一稳妥方式 |

---

## 12 与本机（基准机）的差异要记录

另一台机器采完之后，**两份采集索引会不同**（手机版本、采到的场景都不同）。
合并回主库时按这个顺序：

1. 先比 `场景全集.csv` 的「已采」列，确认哪些是新的；
2. 只搬 `资源库/场景库/<新章节>/<新场景>/` 整个目录，**不要覆盖本机同名的已验收场景**；
3. `registry.json` 用脚本合并（`collect_all` 写的是「读-改-写」，两份直接覆盖会丢键）：
   ```bash
   python -c "
   import json,sys
   a=json.load(open('资源库/场景库/registry.json',encoding='utf-8'))['scenes']
   b=json.load(open('另一台/registry.json',encoding='utf-8'))['scenes']
   for k,v in b.items():
       if k not in a: a[k]=v
   json.dump({'scenes':a},open('资源库/场景库/registry.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
   print('合并后',len(a))
   "
   ```
4. 跑 `gen_catalog.py` 重生成三张表单，再 `paths.py --check`。

---

## 13 相关文档

| 文档 | 讲什么 |
|---|---|
| [`09-拆包数据源勘察.md`](09-拆包数据源勘察.md) | 客户端数据分布、提取链路、数据表地图、已知缺口 |
| [`10-存储规范与场景库.md`](10-存储规范与场景库.md) | 四层目录契约、场景卡与 registry 双门禁、十个坑 |
| [`01-场景还原.md`](01-场景还原.md) | 从 bundle 到三角面：世界矩阵、压缩网格、精度校验 |
| [`04-跨章节对照.md`](04-跨章节对照.md) | **换章节前必读**：7 处要改，2 处会静默产出空几何 |
| [`../PROMPT.md`](../PROMPT.md) §20 | 存储规范与场景库的完整约束（S1~S8、R5~R10） |
| [`../工具/采集/README.md`](../工具/采集/README.md) | 采集层脚本逐个说明 |
