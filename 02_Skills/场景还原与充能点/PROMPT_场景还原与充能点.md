# NIKKE 地图 · 场景还原与充能点 · 执行 Prompt

> **版本**：v1.0（2026-10-27，从第 34/35 章两轮实战反推固化）
> **场景**：拿到一个战斗区域名（`fcbg_*` / `sbg_*`），从游戏客户端 bundle 一路做到「可交互充能点页面」
> **上位契约**：`F:\Codex\Nikke\AGENTS.md` · `..\AGENTS.md` · 方法细节见 `..\docs\01-场景还原.md` 与 `02-充能点算法.md`
> **本场景定位**：**主链路技能（S-MAP）**。完整七步，每步都有机器可验的通过条件。
> **不做**：不做伤害模拟、不做敌人行为、不做关卡→背景映射（客户端不存在这张表）

---

## 0 一句话任务

把「某区域的一张战斗背景」变成「玩家站在掩体后、准星该指向哪一像素」的**像素级答案**，
且每个数字都能用独立实现复算。

链路固定七步，**顺序不能改**：

```
bundle ──①装配──▶ assembly_*.json ──②glTF──▶ .glb（三维可看）
                          └──③选点──▶ px_*.json ──④可信度──▶ ⑤审计 ──⑥轮换──▶ ⑦出页面
```

---

## 1 动手前先定位三件事（错了会整轮返工）

### 1.1 章节号只认 `chapter` 字段

`CampaignChapterTable` 的 `id` 是**主键**，真正的章节号是 `chapter`（= `chapter_id − 1`）。
用剧本名交叉验证：

| 区域 | chapter_id | chapter | 剧本 | field_id |
|---|---:|---:|---|---|
| 沼泽丛林 | 36 | **35** | `d_main_35_*` | `fcbg_swamplandjungle_001` |
| 晶化城市森林 | 35 | **34** | `d_main_34_*` | `fcbg_cityforestcrystal_007` |

> 2026-10-27 就是取了 `id`，把沼泽标成 36 章、晶化标成 35 章，页面/文档/查看器全部返工。

### 1.2 战场是「全集」不是「某一关」

客户端**没有** stage → 具体背景的映射：

- `CampaignStageTable` 只有服务端下发的 `spot_id`
- `campaignlevelmapgroup_assets_fcbg_*` 的 MonoBehaviour 只有 `_stageId` + 坐标
- `spotsetting` bundle 里只有一个全局相机设置

所以只能给「本章战场全集」，具体哪一关用哪张背景**必须人工开背景认图**。不要承诺「3-7 关就是第 2 张图」。

### 1.3 素材在哪条链路

| 情况 | 做法 |
|---|---|
| 有编号（`001`~`005`）的常规场景 | `build_assembly.py <bundle> <out.json>` 直指文件 |
| 只知道场景名（新区域） | `extract_sbg_cf.py <场景名>` 批量抓 hd 主场景，**排除** `_rightclear` / `_midclear` 变体与 `(sd)` 版本 |
| boss 背景 | 场景名后缀 `bbg`（如 `swamplandjunglebbg`），落 `原始bundle/sbg_boss/` |

---

## 2 七步链路

### ① 装配：bundle → `assembly_<id>.json`

```bash
PY=/c/Users/Administrator/.workbuddy/binaries/python/envs/default/Scripts/python
cd 数据
$PY build_assembly.py 原始bundle/sbg/sbg_swamplandjungle_001.bundle 导出/assembly_001.json
```

**验收（这一步唯一会静默算错的）**：

| 检查 | 通过条件 | 失败含义 |
|---|---|---|
| **三角面 / 顶点比** | **≥ 1.5** | < 1.5 就是踩了 `z=zmin` 过滤 —— 侧壁丢一半，遮挡失效、段数虚高 |
| `*_col` 是否过滤 | ground 计数应减少 | 没滤 → 射线撞隐形地板，段数全归零 |

实测：全取顶点 1.88、只取一层 0.91（三角形只剩 24.5%）。
`SHEET_ONLY=1` 是**单面平板专用**的减半优化，盒状件**绝不能**开。

### ② glTF：`assembly_*.json` → `.glb`

```bash
$PY dump_textures.py 001        # 新版用这个；c 系列用 dump_tex_cf.py
$PY export_glb.py 001
```

贴图必须先于 glb 导出，glb 从 `素材/` 取图。

**alpha 分流（必做）**：按不透明像素占比决定 `alphaMode`
—— ≥50% → `MASK`（树叶/栅栏），否则 → `BLEND`（雾片/光斑）。
一律 MASK 会把 `*_fog01`（alpha 均值 0.16、86% 像素 <128）糊成不透明灰块。

### ③ 选点：`px_<id>.json`

```bash
$PY scan_px.py 001                 # 默认 cover_3 = 游戏进图位置
$PY scan_px.py 001 --view=cover_1  # 别的阵位（见 S-VIEW 技能）
```

内部逻辑：相机在 `cover_N.camera_position`（身后 4.5m / 视高 2.34m / FOV 60）→
深度图 → 逐像素反推枪口角 → 命中计数 → 稳定半径 → 像素 NMS。

### ④ 可信度（300 次扰动）

```bash
$PY verify_px.py 001 --sim=300
```

扰动项：站位 ±0.30m / 枪口高 ±0.15m / 手抖 ±2~4px / 后坐 0.12° / 几何 1.5px。

> **`verify_px.py` 会整份重写 `px_*.json`** —— 所以它必须排在 `sim_charge.py` **之前**。
> 跑到后面会把轮换结果冲掉（c005 踩过一次）。

### ⑤ 独立审计

```bash
$PY audit_px.py 001
```

六项：代码往返自洽 ≤0.03px、容错锥、五阵位可用性、俯角、宽高比、首击物尺寸 → 分 **S/A/B/C/D**。

### ⑥ 轮换模拟

```bash
$PY sim_charge.py 001
```

输出池子占比 / 发数 / 贪心重排。**池子 × 2.8% = 打地形的充能上限**。

### ⑦ 出页面

```bash
$PY gen_fp_page.py          # 35 章
$PY gen_cf_page.py          # 34 章
$PY gen_mw_page.py          # 母鲸
```

全阵位版本走批处理，**不要手写循环**：

```bash
$PY batch_views.py --jobs=6     # scan→verify→audit→sim，7 战场 × 5 阵位
$PY render_views.py --force     # 35 张纯场景图 → render/fp_<arena>_cover_<N>.webp
node check_page_marks.mjs       # 真机验证
```

---

## 3 换区域必查五条

```
① 三角面/顶点 ≥ 1.5        → 否则侧壁被丢（唯一会算错数的）
② 有无 *_col 碰撞网格      → 有就过滤
③ 包里有 Camera 对象吗      → 没有就用锚点 + fov 60，camera 写 null
④ 档位来源是 root 节点名吗  → 不是 CollisionGradeType，也不是文件名前后缀
⑤ alpha 走 MASK 还是 BLEND  → 按不透明像素占比分流
```

详见 `..\docs\04-跨章节对照.md` §3。

---

## 4 交付前的自检清单

- [ ] `px_*.json` 里每条点位都有 `px`（1600×900 基准）、`n_steady`、`n`、`chain`
- [ ] `verify.field_sim` 存在且 `pool_pct` 有值（空战场允许 0，但不能缺字段）
- [ ] `audit_*.json` 的 `rows` 条数 == `points` 条数
- [ ] 页面图片引用全部存在（`grep -o 'src="[^"]*"'` 逐个 `-f` 判断）
- [ ] 页面 `<title>` 章节号与 `chapter` 字段一致
- [ ] 16:9 以外的拉伸提示保留在页面上

---

## 5 踩坑（都踩过，别再踩）

| 坑 | 表现 | 处置 |
|---|---|---|
| 系统 `python` 无 UnityPy | `ModuleNotFoundError` | 用 `~/.workbuddy/binaries/python/envs/default/Scripts/python` |
| `/tmp` 在 Windows bash 不可用 | 对比文件写不出来 | 用 `_cmp/` 目录或 `git show HEAD:path >` |
| Chrome 截图加载旧 glb | 改了不生效 | URL 加 `?v=${Date.now()}` |
| 8899 双实例 | curl 经环境代理返回 502 | `taskkill` 后单实例 + `curl --noproxy '*'` |
| `slots.json` 相机多一层数组 | `[[-4.8,0,0]]` 取 `C[0]` → NaN → 整图变灰但脚本报成功 | 取 `camera_position[0]`；出图脚本加空白检测（<200KB 报错） |
| `sim_charge.py` 空战场 | `IndexError` | 0 个达标点时写全 0，不跳过 |
| `audit_px.py` 空集 | `max() empty` | `perp_med/perp_max` 判空 |
| 串行批处理 | 35 组 87 分钟 | 组间并行 6 路 → 16 分钟 + 断点续跑 |

---

## 6 产物

| 类型 | 路径 |
|---|---|
| 装配 | `导出/assembly_<arena>.json` |
| 点位 | `导出/px_<arena>.json`、`导出/px_<arena>_cover_<N>.json` |
| 审计 | `导出/audit_<arena>.json` |
| 阵位坐标 | `导出/slots.json`（15 个战场共用一套布局） |
| glTF | `导出/arena_<arena>.glb`（gitignore，可重生成） |
| 页面 | `H35沼泽丛林玩家视角充能点.html` 等 |
