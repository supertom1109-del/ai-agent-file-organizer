# 隔离试跑 · Windows 系统回收与恢复

批次目录为 `{批次目录}`。读取 `before.json` 和 `plan.json`，请用户确认仅对本批新建的一个虚构测试文件做一次系统回收和一次原位还原。既有回收条目、用户文件和系统设置都在授权范围之外。过程记录只写 `records/`；保留失败现场，禁止永久删除或清空回收站。

1. 在动作发生前运行 `python -X utf8 "{工具目录}/rehearsal.py" capacity --run "{批次目录}"`。工具只查询当前用户的匹配配置与源卷占用。结果写入 `records/quota.json`。必须有实测配置、正数配额、非永久删除设置和足够余量。读不到或只有估值就保留样例，标记 `blocked_preflight`。
2. 预检样例范围、指纹、回收记录读取权限与 Windows 还原入口。通过系统回收接口送入回收站；程序方式明确指定 `SendToRecycleBin`，有永久删除提示时停止。分别实测原路径在操作前和操作后的状态。
3. 按原路径、操作时间、同后缀索引 `$I` 与内容实体 `$R` 精确匹配本次对象。读取内容实体并验证指纹与大小。保存匹配索引的原始字节为 `records/recycle-index.bin`。证据不足时记 `uncertain` 并保存现场。
4. 确认原位为空，只对已定位对象执行 Windows「还原」。实际读取原位文件并核对指纹、大小和修改时间。复查对应用户可见条目及内容实体已离开回收站。只有索引残留时单列记录并保持原样。工具返回值或聚合条目数只作辅助。

提交 `records/ops.jsonl`，每行含带时区的系统时间 `time`、`phase`、`path`（计划样例）和 `result`、`evidence`。成功记录：
- `quota / preflight_passed`，时间用 `quota.json` 的 `checked_at`，证据指向实测文件。
- `before_recycle / sampled`，证据含 `exists_before`。
- `after_recycle / recycled_verified`，证据含 `exists_after`、`index_name`、`entity_name`、`entity_sha256`、`entity_size`。
- `after_restore / restored_verified`，证据含 `exists_after`、`shell_entry_count_after`（本次匹配对象数量）、`restored_sha256`、`restored_size`。

`records/after.json` 格式为 `{"entries":{"work/文件路径":{"sha256":"实测指纹","size":0,"mtime_ns":0}}}`，使用正斜杠和实测整数。`records/run-notes.md` 记录配额来源、系统入口、异常、恢复和残留。禁用或失败的步骤按实际交付，不写成功。
