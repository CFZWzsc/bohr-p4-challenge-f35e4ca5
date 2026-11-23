---
name: figure-axis-calibrator
description: Use when a scientific figure must be read into numbers — calibrate axes from tick marks (linear or log), convert pixel positions to data values with units and precision, and emit /app/output/result.json preserving case_id and every output_contract field.
---

# 科研图表坐标标定与数据提取

## 用途与适用条件

把一张科研图（或一组子图）的结构化读数转成带单位、带精度、可复算的数据：先由刻度标定坐标轴（线性/对数/双轴），再把像素坐标换算为数据值，输出系列表、趋势与峰位、误差线与证据定位。

适用于：折线/散点/柱状/箱线图的数值化、光谱峰位读取、多子图分别标定。以下情形必须如实降级而不是编造：只有位图没有任何刻度信息、图被裁剪导致刻度缺失、图例与系列无法对应、单位未标注。此时输出 `status=partial`，在 `needs` 中列出补齐标定所需的最少信息。

本 Skill 不负责识别图中物质的科学身份，也不从曲线形状推断机理。

## 输入

- `/input/case.json`（可用 `--case`）：包含图表读数。脚本按以下顺序查找：
  - `chart` / `figure` / `charts[]` / `figures[]` 中的对象；
  - 对象内 `axes.{x,y}`：`scale`、`ticks[]`（`{pixel, value}`）、`unit`、`label`；
  - `series[]`：`name`、`legend`、`points[]`（`x_px`,`y_px` 或 `x`,`y`）、`err_lower_px`/`err_upper_px`、`source`。
- `task.md`：优先 `/input/task.md`，其中对字段、单位、精度的要求优先。
- 图片：`image`/`image_path` 只登记文件名；像素读数由调用方按第 0 步从原图读出后写入 `case.json`；原表逐格转成 `tables[]`。

## 处理流程（对应评分维度）

0. **读原图取数（实际效果的前提）**：打开案例原图，按子图记录刻度像素位置与刻度值、每系列点的像素坐标、误差线端点像素、图例文字、显著性标记、比例尺、图注与子图编号，写成 `/app/work/case.readings.json`（`case.json` 副本补齐 `ticks`/`points`/`source`）。目视不能确认的刻度或点不得估造，记入 `needs`；原表逐格抄录并标注来源，不做推算。
1. **轴类型判定（实际效果、创新增益）**：读取声明；若未声明，用刻度值判断——像素间隔近似等距且数值比值恒定 → 对数轴；否则线性。判定结果与依据写入 `calibration.type_basis`。
2. **标定拟合（结果正确性）**：以刻度点为样本做最小二乘。线性：`value = a*px + b`；对数：`log10(value) = a*px + b`。输出斜率、截距、拟合残差最大值与 R²；刻度少于 2 个时失败关闭。
3. **精度与单位**：按刻度最小间隔计算可报告小数位（`precision_digits`），保留输入单位不做隐式换算；单位缺失时 `unit=null` 并列入 `needs`。
4. **点换算与误差线**：每个点换算为 `x`,`y`；若给出误差像素，按同一条标定换算为数据误差；范围值保持上下界，不取平均。
5. **系列级结论**：点数、范围、最小二乘趋势斜率（含单位/像素换算）、局部峰（相邻点比较，最多 5 个）、显著性与比例尺等非数据元素只在输入显式给出时记录，不臆测。
6. **证据定位（可核验性）**：每个系列记录 `axis_ids`、使用的刻度点、点索引范围；每条结论附 `derived_from`。
7. **稳定性（可靠体验）**：全流程无随机；相同输入重复运行结果一致。异常输入进入结构化错误。

## 输出契约

`/app/output/result.json`：

| 字段 | 类型 | 含义与要求 |
|---|---|---|
| `case_id` | string/null | 原样复制输入 |
| `status` | enum | `success`/`partial`/`insufficient_input`/`failed` |
| `result.charts[]` | array | 每子图一项：`chart_id`、`panel`、`caption`、`x_calibration`、`y_calibration`、`series[]`、`elements` |
| `chart.elements` | object | `axes/legend/series/points/error_bars/significance/scale_bar/caption/panel_id` 九项，各为 `{present, where, note}` |
| `calibration` | object | `axis`、`scale`、`slope`、`intercept`、`r2`、`max_residual`、`unit`、`precision_digits`、`type_basis` |
| `series[]` | array | `name`、`n`、`x_unit`、`y_unit`、`points[]`、`trend`、`peaks`、`axis_ids` |
| `points[]` | object | `x`、`y`、`x_px`、`y_px`、`x_err`、`y_err`；误差保留上下界，不取平均 |
| `tables[]` | array | 原表逐格 `table_id`、`cells`、`locator`；无表为 `[]` |
| `claims[]` | array | `claim`、`basis`（`direct`/`inferred`/`undetermined`）、`evidence_ref` |
| `evidence[]` | array | `item`、`location`（如 `Fig.1 panel b, p.3`）、`basis`、`r2` |
| `needs[]`/`uncertainty[]`/`limitations[]`/`errors[]` | array | 缺口、不确定、限制、结构化错误 |
| `stats` | object | `chart_count`、`series_count`、`point_count` |
| `contract_notes` | object | `output_contract` 中保留为 `null` 的字段与原因 |

`output_contract` 声明的每个字段都必须存在，未映射写 `null` 并登记。`panel`、`caption`、`elements`、`tables`、`claims`、`evidence.location` 脚本不产出，由调用 Agent 补齐。示例（结构示意）：
`"evidence":[{"item":"series:A","location":"Fig.1 panel b, p.3","basis":"ticks value 0/10 at pixel 100/300","r2":1.0}]`

## 异常处理

| 情形 | 行为 |
|---|---|
| 只有图片、无结构化读数 | 先执行第 0 步取数；仍缺刻度则 `status=partial`，`needs` 写明缺哪一轴、哪一子图 |
| 刻度 < 2 或像素重复 | 该轴 `error`，系列不换算，`status=partial` |
| 对数轴刻度含 ≤0 | 该轴失败关闭，`errors` 记录原因 |
| 图被裁剪 / 过曝 / 分辨率不足 | `elements.<项>.note` 与 `uncertainty` 记原因，只报可见范围，不外推 |
| 图例缺失或与系列冲突 | 两方都保留并标 `conflict`，不合并、不猜配对 |
| 曲线重叠无法分辨 | 标 `overlap`，只给可分辨段，其余入 `needs` |
| 单位不明 | `unit=null` 并列入 `needs`，不假定量级 |
| 点坐标缺失/非数值 | 跳过该点并列入 `uncertainty`，不补 0 |
| 输出失败 | 仍写出结构化 `result.json`；脚本恒定以退出码 0 结束，状态以 `status` 为准 |

## 限制与不适用

- 脚本不做像素级 OCR、曲线跟踪或颜色聚类；读数由调用方从原图取得并写入 `case.json` 后再标定。
- 不判断科学结论与机理；不做单位换算（只保留并标注）。
- 双轴/双子图必须分别给出各自标定，否则按缺口处理。

## 最小调用示例（示例）

以下为接口示意，**非官方固定案例结果**。

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /input/case.json --out /app/output/result.json
```

合成输入（示例）：

```json
{"case_id":"synthetic-chart","chart":{"axes":{"x":{"scale":"linear","ticks":[{"pixel":100,"value":0},{"pixel":300,"value":10}],"unit":"s"},"y":{"scale":"linear","ticks":[{"pixel":400,"value":0},{"pixel":200,"value":5}],"unit":"mV"}},"series":[{"name":"A","points":[{"x_px":200,"y_px":300}]}]},"output_contract":{"series":"array","status":"string"}}
```

示意输出片段：`{"case_id":"synthetic-chart","status":"success","result":{"charts":[{"chart_id":"chart-1","series":[{"name":"A","points":[{"x":5.0,"y":2.5}]}]}]}}`（仅演示结构与单位方向，不代表任何官方评分）。

## 调用与自检

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /app/work/case.readings.json --out /app/output/result.json
```

`--out` 与 `--output` 等价；默认 `/input/case.json` → `/app/output/result.json`。脚本只做标定与换算；`elements`、`claims`、`tables`、`evidence.location` 由调用 Agent 在同一 `result.json` 中补齐，不能只交脚本骨架。

- [ ] `case_id` 与输入一致；`output_contract` 每字段存在（未映射为 `null` 并登记）。
- [ ] 每轴有 `scale`、`type_basis`、`r2`；对数轴判定有刻度比值依据。
- [ ] 每个值带单位与 `precision_digits`，未做未声明换算；误差线同标定换算、不取平均。
- [ ] `elements` 九项齐全，缺失项区分“原图没有”与“本次读不到”。
- [ ] 每条结论在 `claims.basis` 中标注直接可读/推断/无法确定；无依据写 `undetermined`。
- [ ] 每个系列与数值有 `location` 可指回子图/图注/页码；无标定信息时 `status=partial` 且 `needs` 完整。
- [ ] 不编造读数、页码或评分；不同子图不混编号。
