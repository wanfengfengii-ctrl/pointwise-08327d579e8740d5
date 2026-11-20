# 澄岳往复载荷磨耗台账

澄岳材料试验室用这套台账把试验台的具名原拍转换为可复核的磨耗逐笔账。白班冻结读数和切班计划，夜班在源站关库后收齐固定件并签报，复核员按号领取原始签存结论。

## 日常工作

1. 录入试验号、准确校准比例、班段及带出处的原拍。
2. 按输入拍序核对必需字段和连续性，精确换算 kN，冻结测量与切班计划。
3. 从指定冻结修订发行各班固定件。相同修订和班段可重复领取已登记的固定件。
4. 把预期清单和固定件交给离线中心。中心支持乱序收件，相同固定件重投复用实收身份并返回当前齐备状态。
5. 齐件后按原拍顺序恢复全轮转折及出处。接缝同值可延续平台，同向锚点在计量前消除。
6. 完整循环先按消除顺序记账，余下半循环再按原拍顺序结算。幅值分档使用同一逐笔账。
7. 报告记录修订、按拍序排列的父件、精确档界与磨耗账，并与成功回执一起提交。
8. 更正另建修订。源站关闭及中心重开后仍可按原报告号领取或导出原签存内容。

## Python 3.11 标准库接口

在项目根目录运行。源站使用一个 SQLite 文件，中心使用另一个。`RevisionStore` 与 `IssueRegister` 可分别连接源站文件。`AdmissionStore` 与 `ArchiveStore` 可分别连接中心文件。存储对象提供 `initialize()` 和 `close()`。重复初始化保留原资料、用户更正、发行件、实收及历史档案。演示显式加载样例。

```python
from archive.export import export_report
from archive.publication import publish
from archive.reports import read
from archive.store import ArchiveStore
from issue.register import IssueRegister, issue_segment
from receive.admission import receive_segment
from receive.coverage import ExpectedManifest
from receive.store import AdmissionStore
from trial.calibration import Calibration
from trial.plan import SegmentSpec, TrialPlan
from trial.revisions import freeze
from trial.samples import RawSample
from trial.store import RevisionStore

source = RevisionStore('source.sqlite')
register = IssueRegister('source.sqlite')
source.initialize()
register.initialize()
plan = TrialPlan('CY-017', (SegmentSpec('day', 1, 2), SegmentSpec('night', 3, 3)))
revision = freeze(source, plan, Calibration('2'), (
    RawSample(1, '0', 'bench/1'), RawSample(2, '2', 'bench/2'), RawSample(3, '0', 'bench/3'),
))
expected = ExpectedManifest.from_revision(revision)
wires = [issue_segment(source, register, revision.revision_id, spec) for spec in plan.segments]
source.close()
register.close()

admissions = AdmissionStore('center.sqlite')
archive = ArchiveStore('center.sqlite')
admissions.initialize()
archive.initialize()
manifest_id = admissions.register_manifest(expected)
for wire in reversed(wires):
    arrival = receive_segment(admissions, manifest_id, wire)
signed = publish(admissions, archive, manifest_id, [0, 2, 4])
original = read(archive, signed.report.report_id)
json_document = export_report(archive, original.report.report_id)
admissions.close()
archive.close()
```

- `freeze` 返回固定 `Revision`，`load_revision` 可按 `revision_id` 重读。原拍必须非空，拍号为连续整数且保留输入顺序。班段为连续互斥的闭区间，必须覆盖实际首末拍。缺拍、重复拍、非法覆盖、缺失出处或非法数值抛出 `ValueError`，无新增修订。
- `issue_segment` 接收段名或需准确匹配的 `SegmentSpec`，返回固定 JSON 文本。未知修订或不匹配的段抛出 `KeyError`，无新增发行。V1 外层使用 `version`、`piece_id`、`provenance` 和 `evidence`。固定身份绑定正文。正文保留两侧异值支持的局部转折和必要的首尾平台证据。全平件保留平台的实际首末，原始读数行留站。
- 用指定冻结修订的 `ExpectedManifest` 调用 `register_manifest`。清单只含试验、修订、首末拍及切班信息。`receive_segment` 返回实收身份和 `status`，可读取 `status.ready` 与 `status.missing`。混版、越界和同槽异件抛出 `ValueError`，实收保持原状。未知清单抛出 `KeyError`。`build_manifest` 可查询已实收件及覆盖状态。
- `publish` 返回 `PublishedReport`。缺件抛出 `IncompleteManifest`，非法档界抛出 `ValueError`。可选的 `before_commit` 无参回调在报告和回执暂存后执行，抛出的异常会撤销本次发布。失败后可沿同一入口重试。
- `read` 和 `export_report` 仅取签存快照。未知报告号均抛出 `KeyError`。导出保留原拍号与出处、有序父件、精确幅值、权重、档界、档计数和成功回执。未设上限的档用 JSON `null`。

## 计量口径

数值输入接受整数、有理数字符串或 `Fraction`，换算与核账均用 `Fraction`。JSON 中精确数值写成有理数字符串。缺失或不可精确解析的输入会拒绝。计算确定，分段方式和到件顺序可以更换，固定同一拍序、校准及档界即可复现逐笔账。

同值内部平台成为转折时归最后一拍。首末边界保留实际首末原拍。每轮从尚未消除的序列找最靠前的连续四点，若两内点的绝对差为正且不大于左右相邻绝对差，则按两内点记一笔权重为 1 的完整循环并移除两点，随后重新查找。无合格窗口时，剩余相邻非零幅值按拍序记为权重 `1/2` 的半循环。全平和单拍试验保留零账。档界严格递增，零可显式给出，也可从第一个正切点补齐。各档左闭右开，最后一档无上界。

七拍样例 `0、4、4、4、1、3、0 kN` 在第 3、6 拍后切班。整轮转折拍为 `1、4、5、6、7`。拍 5 和 6 记一笔 `2 kN` 完整循环，拍 1 和 4、拍 4 和 7 各记一笔 `4 kN` 半循环。档 `[0,2)`、`[2,4)`、`[4,+∞)` 的计数为 `0、1、1`。

## 回归与演示

```sh
python3 -B check_project.py
python3 -B demo.py samples/seven_shots.json
```

完整回归覆盖精确冻结、缺拍和重叠覆盖、乱序实收及重投、混版和越界、离线切班不变性、并列窗口顺序、精确压线、签报失败重试及历史领取。演示用临时目录创建两份数据库，关闭源站后接纳和签报，重开档案核对导出，再输出经独立样例断言核对的实际明细和下游数据。
