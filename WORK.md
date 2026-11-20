# 磨耗做功交接

现有台账的 V1 操作和样例见 README.md。白班仍照原规程录入载荷和切班，新增同步交付已校准的行程。夜班收齐指定试验的新版段件后签做功账。源站与中心继续各用独立的数据库文件。

## 调用约定

| 入口 | 输入与返回 |
| --- | --- |
| `trial.revisions.freeze_work(store, plan, calibration, samples, travel_mm)` | 前四项沿用 `freeze`。`travel_mm` 以整数拍号为键，恰好覆盖本次全部原拍，每个值为该拍已校准的毫米读数。随原测和切班一起冻结。返回可交给 `ExpectedManifest.from_revision` 的修订，保留 `revision_id`、`plan` 和首末拍。 |
| `issue.register.issue_work_segment(revision_store, register, revision_id, requested)` | 凭带行程的确切冻结号和段名或对应 `SegmentSpec` 发行 V2 JSON 文本。同一冻结和班段复领原固定字节，重开源库后也可领。 |
| `receive.admission.receive_work_segment(store, manifest_id, wire)` | 清单仍用 `ExpectedManifest.from_revision` 创建并交 `AdmissionStore.register_manifest`。返回与 `AdmissionResult` 同式的首纳 `identity` 和当前 `status`。可乱序收件。同一固定正文即使只是 JSON 排版变化，重投也返回原身份和当前齐备状态。同槽异件拒收。 |
| `archive.publication.publish_work(admissions, archive, manifest_id, band_edges, *, before_commit=None)` | 凭指定实收清单签发。档界与原 `publish` 相同。返回带 `report.report_id`、回执及 `to_data()` 的签报对象。无参 `before_commit` 与 V1 同义，在正文及回执暂存后执行，抛出的异常撤销本次发布。 |
| `archive.reports.read_work(archive, report_id)` 与 `archive.export.export_work_report(archive, report_id)` | 前者按号领回同式签报对象，后者返回等价 JSON 文本。两者读取原签存数据。 |

行程输入接受非布尔整数、有理数字符串或 `Fraction`。行程可相等、下降或为负。载荷仍按原校准换算为 kN。更正另建冻结，已经发行和签存的内容可独立复领。

V2 段件有整数 `version` 值 `2`、`piece_id`、按原规程绑定试验、确切修订、段名与闭拍域的 `provenance`，以及计量证据。固定身份覆盖版本、来源及完整证据。证据须保全 V1 可出站锚点的载荷和出处、这些锚点上的行程及足够的原路径积分信息。锚点包括局部转折和首尾平台的原有边界拍，同拍只表示一个物理观测。原始测量行和其他拍的行程留站。证据结构可自行选择。中心校验版本、身份、正文和指定清单的匹配，拒绝拍位或锚点失配及无法按所用证据格式解释的正文。签发使用齐备的同修订 V2 实收件，父件按拍序固定。V1 和 V2 分别使用本版入口和冻结号，V1 原格式、接口及历史保持兼容。

非法输入、非法规格、坏件、冲突和混版报 `ValueError`。签发遇缺件报 `receive.manifest.IncompleteManifest`。合法但不存在的修订、段名、清单或报告号报 `KeyError`。拒绝和提交失败不留下本次部分结果，已有实收和旧报告可继续使用。

## 计量与交账

令原相邻拍的载荷为 `f₁`、`f₂`，行程为 `x₁`、`x₂`。该边做功为 `(f₁ + f₂) × (x₂ − x₁) / 2`，单位是 J。整轮总做功是原相邻边之和。接缝按真实相邻拍计入一次。按 V1 口径处理内部平台、实际首末拍和局部转折，归并时仍保留被跨过的路径做功。

四点消除的资格和顺序沿用 V1。一个完整循环的做功是当时从第一个内点到第二个内点沿有效路径的积分，减去按同一端点公式求得的直连弦做功。结算后两内点退出转折序列，余路径用这条弦替换两内点之间的路径，两侧做功仍归余路径。后续循环和半循环均以当时有效路径计量。每笔半循环记录对应余段的实际做功，计数权重仍用于磨耗分档。零幅值余段不新增磨耗笔数，其做功仍计入余路径总量。完整循环做功之和加余路径总做功等于整轮原路径做功。

导出沿用 V1 的 `report` 与 `receipt` 两层。`report` 保留原报告号、清单号、试验号、固定修订号、按拍序的实收父件、归一档界、逐笔循环和分档。新增 `total_work_j` 与 `remaining_work_j`，每条 `cycles` 记录新增 `work_j`，其余原字段仍依 V1。JSON 精确量用归约有理数字符串，例如 `0`、`-2` 或 `79/2`。正文及对应回执一同提交。勘误、关源和中心重开后按原号领取和导出当时存值。

## 样例与核验

`samples/work_cases.json` 每个样例包含冻结用试验号、比例、具名原拍与行程。`segment_endings` 的每一组是独立切班方式，含末拍，下一段紧接上一段末拍。`expected.cycles` 的各行是起拍、止拍、幅值、权重和有符号做功。`band_counts` 对应归一档界。八拍样例做整件及四段逆序接纳，峰平台归第 3 拍，两笔完整循环依次为 1/2 J 与 −2 J，半循环及余路径均为 79/2 J，原路径为 38 J。将全部行程取反时，做功反号而磨耗计数照旧。两个三拍例的出站锚点同值且同位置，中间拍行程留站，原路径分别为 2 J 和 3 J。全平例没有磨耗笔数，仍签 12 J。单拍原路径与余路径均为零。

继续使用 `.pointwise-runtime.json` 的版本 1 和 `cli` 类型，其中 `setup` 为命令参数数组的列表，`verify` 与 `demo` 各为一条命令的参数数组。交付时让 `verify` 跑完整原回归并核对断源做功账，失败以非零退出。让 `demo` 展示分班乱序实收、关源签发和重开领回的实际结果。原回归和原七拍演示继续可单独运行。

```sh
python3 -B check_project.py
python3 -B demo.py samples/seven_shots.json
```
