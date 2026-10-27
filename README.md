# NIKKE 地图充能点计算

从 NIKKE 客户端拆包，还原战场原生装配，按实机相机逐像素反推「一枪能穿几个可破坏物件」，
输出玩家视角的充能点标注页。

目前覆盖 **四批共 18 套战场**：

| 区域 | 章节 | 战场 | 页面 | 精度 |
|---|---|---|---|---:|
| 沼泽丛林 `swamplandjungle` | **第 35 章** | `sbg_001`~`005` + boss `bbg008` / `bbg009` | `H35沼泽丛林玩家视角充能点.html` | ±1 px 级 |
| 晶化城市森林 `cityforestundercrystal` | **第 34 章** | `sbg_cityforestundercrystal_001`~`005`（`c001`~`c005`） | `H34晶化城市森林玩家视角充能点.html` | ±1 px 级 |
| 母鲸领域 `motherwhalefield` | 第 39 章（H39-40） | `sbg_mw001`~`003` | `H39-40母鲸领域充能点.html` | ±1 px 级 |
| 城市林地 `cityforest` | 第 47 / 48 章 | `sbg_cityforest_001`~`003` | 见 `docs/04-跨章节对照.md` | ±1° 级 |

> **章节号按 `CampaignChapterTable.chapter` 字段，不是 `id` 主键**（`chapter = chapter_id − 1`）。
> 旧文件名里的 `H36-35` 是「chapter_id 36 / chapter 35」的意思 —— 章节号一直是对的，中文标题写错了：
> 沼泽丛林 = **35 章**（`fcbg_swamplandjungle_001`，剧本 `d_main_35_*`），
> 晶化城市森林 = **34 章**（`fcbg_cityforestcrystal_007`，剧本 `d_main_34_*`）。
> 35 章 Boss 是**圣甲虫**，Boss 关落在 `6035044`（`d_main_35_09_s`，`monster_id 13100101`），
> 对应战场 `sbg_swamplandjunglebbg008` / `bbg009`，两张都已还原并进三维查看器。

双击 `启动战场查看器.bat` 会在 8899 端口起本地服务并打开页面（三维视图需要 http 才能加载 glTF）。
三维查看器的战场下拉框已按区域分组，可直接切到 `c001~c005` / `bbg008` / `bbg009`。

> cityforest 三套走的是**反向枚举**（枚举枪口角 → 反投影像素），精度低一档但跨分辨率更稳。
> 两批数据的差异与修订见 [`docs/04-跨章节对照.md`](docs/04-跨章节对照.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/01-场景还原.md`](docs/01-场景还原.md) | 拆包 → Transform 世界矩阵 → 三角面集合 + 相机 + 锚点，含精度校验与已知近似 |
| [`docs/02-充能点算法.md`](docs/02-充能点算法.md) | 充能公式实证、像素级选点、稳定半径、掩体三层、遮挡截断、像素 NMS、可信度、轮换、六项审计 |
| [`docs/03-实例.md`](docs/03-实例.md) | 八图规模、Top1 全链路、案例拆解、分级分布、轮换发数、复核命令 |
| [`docs/04-跨章节对照.md`](docs/04-跨章节对照.md) | **两批 11 套的逐字段对照**：7 处必须修的地方（2 处会静默产出空几何）、两套稳定判据的换算、池子不能跨区域外推 |
| [`docs/05-第34章.md`](docs/05-第34章.md) | 第 34 章（晶化城市森林）章节定位、还原命令、五图规模、段数与容错互斥、每图推荐点与穿透链、可信度/轮换/限制（§5~§7 逐点数字是旧几何，现行看页面） |
| [`docs/06-第35章沼泽丛林.md`](docs/06-第35章沼泽丛林.md) | **第 35 章（沼泽丛林）**：两次纠错的来龙去脉、章节字段定位实证、七张战场规模（含圣甲虫 boss 两张）、63 个点位、图像质量修的三处、已知限制 |
| [`docs/README.md`](docs/README.md) | 索引与一句话流程 |

完整迭代记录（19 节）见 [`PROMPT.md`](PROMPT.md)。

## 结论摘要

### 第 35 章 · 沼泽丛林（63 点）

- 七张战场（5 常规 + 2 boss）全部按**修复后的几何**重算。`z=zmin` bug 修掉后三角面涨 4 倍（001：15,276 → 62,070），
  旧值 130 个点是几何缺口让射线从侧壁穿过去造成的**虚高**，正确值是 **63**。
- 分级 **S 3 / A 2 / B 19 / C 14 / D 25**：001 → 12（最高 4 段，锥中位 4.3px）· 002 → 21（4 段，2.6px）·
  003 → 15（4 段，5.0px）· 004 → 6（2 段，11.1px）· 005 → 9（4 段，1.8px）。
- **圣甲虫 boss**：`bbg008` 受击体 28 件但全画面**没有任何 ≥2 段的共线** → **0 个达标点**，这张图只能打敌人本体充能；
  `bbg009` 受击体 74 件、**6 个达标点**，最高 4 段 `px(242,349)`（50.2m，五阵位全可用），分级 S0 / A1 / B4 / C0 / D1。
- 像素坐标同样只在 16:9 有效。

### 第 34 章 · 晶化城市森林（120 点）

- 分级 **S 4 / A 7 / B 32 / C 17 / D 60**，锥宽中位 **2.8px**，五图池子 **132%~154%**。
- 最硬的结论仍是**段数与稳定性互斥**：五张图的受击体排成 45~55m 细长队列，共线走廊投到屏幕上只有 1~2px 宽。
  每图因此给了**双榜** —— 段数冠军（理论最优，多数按不住）与实战冠军（锥宽 ≥3px 前提下段数最高）。

### 母鲸领域（3 套，旧几何未回归）

点位与分级仍是 `z=zmin` 修复**之前**的值（本地没有 `sbg_mw*` 原始 bundle，无法重跑）。
现状可用但段数偏低，重跑后应普遍上移 —— **这三套数字不要和其他两批横向比较**。

```
沼泽丛林 35 章  63 点   S3  A2  B19 C14 D25   锥宽中位 1.8~11.1px（分图）
晶化城市 34 章 120 点   S4  A7  B32 C17 D60   锥宽中位 2.8px
```

cityforest 三套不能套用上面的分级：可破坏物只有 10~30 件（35/34 章是 63~220 件）、
`hard` 各只有 1 件，池子/需求比大概率 < 30%，**充能点价值本来就低**。

具体推导见 [`PROMPT.md`](PROMPT.md)（§15 像素级选点 / §16 可信度 / §17 战场轮换 / §18 独立审计 / §19 跨章节对照）。

## 目录

```
数据/
  scan_px.py        主脚本：相机深度图 → 逐像素枪口角 → 段数 → 稳定半径 → 选点
  verify_px.py      蒙特卡洛可信度（随机误差进评分，系统性偏差做 OAT）
  audit_px.py       独立审计 A~F 六项 + 分级
  sim_charge.py     战场轮换模拟（池子 / 发数 / 贪心重排）
  scan_best.py      几何内核（射线求交、命中计数、常量）
  build_assembly.py 拆包 → 原生装配 JSON
  extract_sbg_cf.py 按场景名批量提取 hd 主场景 bundle（新区域用这个）
  dump_tex_cf.py    按场景名批量导出 Texture2D
  export_glb.py     装配 JSON → glTF
  gen_fp_page.py    生成沼泽丛林页（第 35 章，含圣甲虫 boss 对照节）
  gen_cf_page.py    生成晶化城市森林页（第 34 章）
  gen_mw_page.py    生成母鲸领域页
  audit_html.py     把审计 JSON 渲染成页面一节
  probe_pixel.py    反查工具：某个像素打到什么
  viewer/           three.js 三维查看器（fp.html 是带点位标注的那个）
  导出/             assembly_*.json（场景装配）、px_*.json（点位）、audit_*.json（审计）
  render/           fp_*.png 无 HUD 机位出图（页面引用）
```

> **cityforest 批次（第 47/48 章）的脚本不在本仓库** —— 那批是在另一个作业目录里内联跑的，
> 产物为 `asm_sbg_00X.json`（装配）+ `charge_multi_sbg_00X.json`（点位），字段名与 `导出/` 下的不同。
> 字段映射见 `docs/01-场景还原.md` §4.1，方法与差异见 `docs/04-跨章节对照.md`。

## 重新生成

```bash
cd 数据

# 1) 拆包 → 场景装配（需要游戏客户端，见 拆包数据源勘察.md）
python build_assembly.py 001
# 2) 装配 → glTF（三维视图用）
python export_glb.py 001
# 3) 像素级选点
python scan_px.py 001          # 或 all / mw
# 4) 可信度模拟
python verify_px.py 001 --sim=300
# 5) 独立审计
python audit_px.py 001
# 6) 出页面（gen_fp_page.py 出第 35 章沼泽丛林页，gen_mw_page.py 出母鲸页）
python gen_fp_page.py && python gen_mw_page.py
```

34 章（晶化城市森林）用的是按场景名批量提取，不走 `build_assembly.py <编号>`：

```bash
cd 数据
# 按场景名抓 hd 主场景，排除 _rightclear / _midclear 变体与 (sd) 版本
python extract_sbg_cf.py cityforestundercrystal    # → 原始bundle/sbg_cf/sbg_cityforestundercrystal_00N.bundle

for n in 001 002 003 004 005; do
  a=c$n
  python build_assembly.py 原始bundle/sbg_cf/sbg_cityforestundercrystal_$n.bundle 导出/assembly_$a.json
  python dump_tex_cf.py $a          # 必须先于 export_glb：glb 从 素材/ 里取贴图
  python export_glb.py $a
  python scan_px.py $a
  python verify_px.py $a --sim=300
  python audit_px.py $a
  python sim_charge.py $a          # 必须在 verify_px 之后，verify 会重写 px json
done
python gen_cf_page.py
```

35 章（沼泽丛林）走同一套按场景名提取，多两条 boss 背景：

```bash
cd 数据
python extract_sbg_cf.py swamplandjungle       # → 原始bundle/sbg/sbg_swamplandjungle_00N.bundle
python extract_sbg_cf.py swamplandjunglebbg    # → 原始bundle/sbg_boss/sbg_swamplandjunglebbg00N.bundle

for n in 001 002 003 004 005; do
  python build_assembly.py 原始bundle/sbg/sbg_swamplandjungle_$n.bundle 导出/assembly_$n.json
  python dump_textures.py $n
  python export_glb.py $n
  python scan_px.py $n
  python verify_px.py $n --sim=300
  python audit_px.py $n
  python sim_charge.py $n
done

# 圣甲虫 boss：bbg008 是开阔水面 0 达标点，bbg009 有 6 个
for b in bbg008 bbg009; do
  python build_assembly.py 原始bundle/sbg_boss/sbg_swamplandjungle$b.bundle 导出/assembly_$b.json
  python export_glb.py $b && python scan_px.py $b && python verify_px.py $b --sim=300
  python audit_px.py $b && python sim_charge.py $b
done
python gen_fp_page.py                          # → ../H35沼泽丛林玩家视角充能点.html
```

`sim_charge.py` 一定要排在 `verify_px.py` 后面 —— `verify_px.py` 会整份重写 `px_*.json`，跑到后面会把轮换结果冲掉（本轮 c005 就踩过一次）。

依赖：`numpy`、`UnityPy`（拆包）、`Pillow`（出图）。

**换章节前必查五条**（详见 `docs/04-跨章节对照.md` §3）：

```
① 三角面 / 顶点 比值 ≥ 1.5     → 实测全取 1.88、只取一层 0.91。低于 1.5 就是踩了 z=zmin 过滤
                                  （侧壁被丢，三角形只剩 24.5%）；2026-10-26 已默认关闭，
                                  需要时 SHEET_ONLY=1 才启用
② 有没有 *_col 地形碰撞网格     → 有就过滤，否则射线撞隐形地板，段数全归零
③ 包里有没有 Camera 对象         → 没有就用锚点位置 + fov 60，camera 字段写 null
④ 档位来源是不是 root 节点名     → 不是 CollisionGradeType，也不是文件名前后缀
⑤ alpha 该走 MASK 还是 BLEND    → 按不透明像素占比分流（≥50% 走 MASK，否则 BLEND）。
                                  一律 MASK 会把 `*_fog01` 雾片糊成灰块（alpha 均值 0.16、86% 像素 <128）
```

第 ① 条是唯一会**算错数**的：cityforest 三套上它把三角形从 15,614 砍到 3,968（只剩 25.4%），
而日志一切正常。修复后与独立实现逐项一致。

## 未纳入版本库的内容

体积大且完全可再生的部分已写进 `.gitignore`，克隆后需自行生成：

| 路径 | 体积 | 生成方式 |
|---|---|---|
| `数据/原始bundle/` | ~165 MB | 从客户端提取（`extract_sbg_cf.py` / `extract_*.py`） |
| `数据/素材/` | ~144 MB | `dump_tex_cf.py` / `dump_textures.py` |
| `数据/导出/*.glb` | ~129 MB | `export_glb.py` |
| `数据/render/` 里除 `fp_*.png` 外的截图 | ~200 MB | 重新截图 |

没有这些也能读页面和所有 JSON，只是三维视图打不开、场景贴图缺失。

## 已知未解决

- **关卡 → 战斗场景的映射不在客户端**。`CampaignChapterTable` 只给章节所属区域（35 章 = `fcbg_swamplandjungle_001`、
  34 章 = `fcbg_cityforestcrystal_007`），`CampaignStageTable` 只有服务端下发的 `spot_id`，
  `campaignlevelmapgroup_*` 的 MonoBehaviour 里也只有 `_stageId` 和坐标。
  所以只能确定「这一章有这么几张图」，具体哪一关用哪张背景要开背景人工认。
- **母鲸三套还是 `z=zmin` 修复前的几何**（本地无 `sbg_mw*` 原始 bundle）→ 重跑时三角面会涨 3~4 倍，段数会上移，需抽查 Top1
- **光照 / 阴影 / 后处理（bloom、vignette、colorAdjust）没有重建** → 三维视图是「贴图原色 + 均匀增益」，
  不是游戏最终成像，颜色只能作参考
- `_nf_*` 近远景背景卡在游戏里走视差滚动，静态放置会露硬边 —— 当前最明显的观感缺陷（`BG_SKIP=1` 可跳过但画面偏空）
- 天空盒只有 side / upper / under 三张，贴球面会极点拉伸
- 相机俯角 / FOV 未标定 → 像素坐标带 ±27px 系统性不确定
- `hpdamage_limit=30` 语义未定 → 轮换模型 A/B 假设差 1 倍
- 敌人 / 队友 / 残骸的实体遮挡未计（不在场景装配里）
- 单发伤害未拆出，换弹未计
- 视差分层位移未验证（`layers.*.scrollWidth` 两批 11 套全部读成 0.0，疑似字段没读到）
- 同场景内同名的可破坏物会被误并成同一件（用 `name` 判同一性）
- 镜头能否左右拖未确认；若能拖，像素坐标系还要多一维自由度
- 八套沼泽/母鲸在 `z=zmin` 修复后未回归（本地无原始 bundle）→ 重跑时三角面会涨 3~4 倍，需抽查 Top1 是否与前值一致
- 35 章受击体排成 45~55m 细长队列，共线走廊在屏幕上只有 1~2px 宽 —— 这是「段数高的点按不住」的根因，
  靠算法消不掉，只能靠站点选择绕开（34 章同样如此，锥宽中位 2.8px）
