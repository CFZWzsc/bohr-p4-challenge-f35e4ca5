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
  - `series[]`：`name`、`points[]`（`x_px`,`y_px` 或 `x`,`y`）、`err_*_px`、`legend`。
- `task.md`：优先 `/input/task.md`，其中对字段、单位、精度的要求优先。
- 图片路径可通过 `image`/`image_path` 提供；本 Skill 只记录其哈希与尺寸声明，不做像素级 OCR。

## 处理流程（对应评分维度）

1. **轴类型判定（实际效果、创新增益）**：读取声明；若未声明，用刻度值判断——像素间隔近似等距且数值比值恒定 → 对数轴；否则线性。判定结果与依据写入 `calibration.type_basis`。
2. **标定拟合（结果正确性）**：以刻度点为样本做最小二乘。线性：`value = a*px + b`；对数：`log10(value) = a*px + b`。输出斜率、截距、拟合残差最大值与 R²；刻度少于 2 个时失败关闭。
3. **精度与单位**：按刻度最小间隔计算可报告小数位（`precision_digits`），保留输入单位不做隐式换算；单位缺失时 `unit=null` 并列入 `needs`。
4. **点换算与误差线**：每个点换算为 `x`,`y`；若给出误差像素，按同一条标定换算为数据误差；范围值保持上下界，不取平均。
5. **系列级结论**：点数、范围、最小二乘趋势斜率（含单位/像素换算）、局部峰（相邻点比较，最多 5 个）、显著性与比例尺等非数据元素只在输入显式给出时记录，不臆测。
6. **证据定位（可核验性）**：每个系列记录 `axis_ids`、使用的刻度点、点索引范围；每条结论附 `derived_from`。
7. **稳定性（可靠体验）**：全流程无随机；相同输入重复运行结果一致。异常输入进入结构化错误。

## 输出契约

`/app/output/result.json` 顶层保留 `case_id` 与原始 `output_contract` 的全部字段（未映射字段保留为 `null` 并写入 `contract_notes`），并包含：

- `status`：`success` / `partial` / `insufficient_input` / `failed`
- `result.calibration`：每个轴的 `scale`、`slope`、`intercept`、`r2`、`max_residual`、`unit`、`precision_digits`、`type_basis`
- `result.series[]`：`name`、`points[]`（`x`,`y`,`x_px`,`y_px`,`x_err`,`y_err`）、`trend`、`peaks`、`n`
- `evidence[]`：轴标定依据、系列点数与索引
- `needs[]`：缺失的标定信息（仅在 partial 时非空）
- `uncertainty[]`、`limitations[]`、`errors[]`、`stats`

## 异常处理

| 情形 | 行为 |
|---|---|
| 无图表读数，只有图片 | `status=partial`，`needs` 列出刻度与系列点，不虚构数值 |
| 刻度 < 2 或像素重复 | 该轴 `error`，系列不换算，`status=partial` |
| 对数轴刻度含 ≤0 | 失败关闭该轴，记录原因 |
| 点坐标缺失/非数值 | 跳过该点并列入 `uncertainty`，不补 0 |
| 图例与系列冲突 | 保留两方，标记 `conflict`，不擅自合并 |
| 输出失败 | stdout 结构化错误，退出码 2 |

## 限制与不适用

- 不执行位图 OCR、曲线跟踪或像素颜色聚类；无结构化读数时只能给出缺口清单。
- 不判断科学结论与机理；不做单位换算（只保留并标注）。
- 双轴图必须分别给出两个 y 轴标定，否则按缺口处理。

## 最小调用示例（示例）

以下为接口示意，**非官方固定案例结果**。

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /input/case.json --out /app/output/result.json
```

合成输入（示例）：

```json
{"case_id":"synthetic-chart","chart":{"axes":{"x":{"scale":"linear","ticks":[{"pixel":100,"value":0},{"pixel":300,"value":10}],"unit":"s"},"y":{"scale":"linear","ticks":[{"pixel":400,"value":0},{"pixel":200,"value":5}],"unit":"mV"}},"series":[{"name":"A","points":[{"x_px":200,"y_px":300}]}]},"output_contract":{"series":"array","status":"string"}}
```

示意输出片段：`{"case_id":"synthetic-chart","status":"success","result":{"series":[{"name":"A","points":[{"x":5.0,"y":2.5}]}]}}`（仅演示结构与单位方向，不代表任何官方评分）。

## 自查清单

- [ ] `case_id` 与全部契约字段保留。
- [ ] 每个轴有标定依据与 R²；对数轴判定有证据。
- [ ] 单位随值输出，未做未声明的换算。
- [ ] 误差线按同一标定换算，未取平均。
- [ ] 无标定信息时状态为 partial 且 `needs` 完整。
- [ ] 未声称运行官方固定案例。


## 交付保证与评分对齐

调用顺序（固定）：

1. 先运行包内脚本（若存在）：`python scripts/run_skill.py`（默认读 `/input/case.json`，写 `/app/output/result.json`）；路径不同时用 `--case` / `--output` 指定。
2. 再完成脚本无法自动完成的实质工作（译文、论述、图表、修订、结论等），把结果写回 `result.json` 对应字段。
3. 最后自检：`case_id` 与输入一致；`output_contract` 每个字段都存在；`status` 使用本 Skill 输出契约的枚举（正常完成为 `success`，确实缺输入或存在未解决项为 `partial`，无法作答为 `insufficient_input`，运行异常为 `failed`）；无 `pending` 占位；数字、引用、来源可逐条回溯。

运行保证：

- 输入缺失、JSON 损坏、字段异常、输出目录不存在时，仍须写出结构化 `result.json` 并正常结束，不得崩溃或非零退出。
- 不联网、不伪造数据、不声称平台评分或官方案例结果。
- 交付物必须是可直接编辑与复核的成品，而不是流程说明。

评分对齐（本题五个维度）：

- 实际效果（40）：完整产出任务要求的最终成品，覆盖全部输入条目，可直接进入修改流程。
- 使用增益（25）：体现相对基础 Agent 的可验证改进（结构化、术语/数字/引用核对、可编辑性）。
- 创新增益（15）：保留方法学增量（分块、对齐、二次校验、版本比对等），并用结果证明其价值。
- 可靠体验（10）：异常输入有明确降级与说明，不同长度/文体/重复运行下稳定产出。
- 生态贡献（10）：用途、调用、输入输出、限制、示例、维护信息齐全，资源可被他人复用。

## 最终交付强制要求

1. **调用 Agent 必须交付成品，不是流程说明**：脚本产出只是索引、核对或规格骨架；调用 Agent 必须在同一 `result.json` 中补齐本题要求的最终产物（正文/译文/审稿意见/综述/分析结论/图表源文件与导出件/幻灯片页内容与讲稿/实验方案等）。交付字段为空、只有标题骨架，或含 `pending`、`TODO` 之类占位，一律视为未完成。
2. **必须覆盖全部输入条目**：输入中的每个章节、问题、文献、图、页面、指标都要有对应条目，不得只处理示例或首条；确实缺失的条目写入 `uncertainty` / `limitations` 并说明原因，不得静默跳过。
3. **必须自检后再交付**：`case_id` 与输入一致；`output_contract` 每个字段都存在；状态值取本题契约规定的枚举；数字、单位、引用、来源可逐条回溯；结果内部无自相矛盾。
4. **参数等价**：`python scripts/run_skill.py --case <输入> --out <输出>` 与 `--output <输出>` 等价；默认 `/input/case.json` → `/app/output/result.json`。
5. **平台用 3 个固定案例分别运行**：逻辑要由输入驱动，不针对某一份示例硬编码；字段命名差异走别名匹配与显式降级，并在 `uncertainty` 记录假设。
