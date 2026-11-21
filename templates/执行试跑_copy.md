# 隔离试跑 · 复制归档

批次目录为 `{批次目录}`。开工先读取独立生成的 `before.json` 及 `plan.json`，逐一重新核实文件大小、SHA-256、可读性和目标占用。本任务只允许在隔离副本的 `work/` 内执行列明的复制，过程记录只写 `records/`。实际动作由用户确认。校验失败的暂存件和空暂存目录保留并登记，冲突原位保留。

1. 逐项按 `copies` 复制到目标卷内的暂存位置，核对指纹，再通过保证目标存在时不覆盖的方式提交到最终路径。暂存留证目录设在 `records/` 内，目标最终可打开且指纹与源相同。将所有正常归档目标的期末状态保存为 `records/copy-first.json`。
2. 按原计划重跑。若目标同内容，核实后跳过。将同一目标集合复测后保存为 `records/copy-repeat.json`。
3. 按 `conflict` 核对同名目标。它应当存在且内容不同，记录拦截。目标原样保留。

提交 `records/ops.jsonl`，每行含 `time`（系统时间及其时区）、`phase`、`path`（源相对路径）、`result`、`evidence`。五行顺序为两条 `normal/copied_verified`、两条 `repeat/skipped_same_content`、一条 `conflict/blocked_conflict`。同组顺序匹配计划。每条证据包含 `target`、`source_sha256`、`target_sha256`。失败如实记录。

两份正常快照及 `records/after.json` 的格式均为 `{"entries":{"work/文件路径":{"sha256":"实测指纹","size":0,"mtime_ns":0}}}`。正常快照只列归档目标；期末快照列 `work/` 的全部文件。使用正斜杠，大小和修改时间按实测整数填写。`records/run-notes.md` 写工具、异常、暂存状态、未决项。保留原始日志与样例。
