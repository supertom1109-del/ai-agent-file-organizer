# 隔离试跑 · 改名与链接修复

批次目录为 `{批次目录}`。开工读取发起方生成的 `before.json` 和 `plan.json`，确认原件指纹、目标未占用、计划中的旧链接均能唯一定位。用户确认后再处理。改名、引用替换和冲突试验只限计划中的 `work/` 路径，记录只写 `records/`。

1. 把被引用文档的期初原文留在 `records/`。确认普通改名前旧路径存在、新路径不存在；采用目标存在时不覆盖的方式提交。改名后复查旧路径已消失，新路径可读取且 SHA-256 一致。
2. 对 `reference_edits` 只改指定 Markdown 链接中的路径。与期初原文逐字节比对，历史名称、链接文字、无关正文、编码和换行保持原样。按所在文档目录解析新链接，实际打开目标并核对指纹。
3. 核对 `conflict` 中已有目标的指纹，双方原件保留；复验 `stable_links` 均能打开。中断时保留动作记录、暂存和原始证据。

提交 `records/ops.jsonl`，每行含带时区的系统时间 `time`、`phase`、`path`、`result`、`evidence`：
- 第一行 `rename / renamed_verified`，`path` 为目标，证据含 `old_path`、布尔值 `old_exists_before`、`old_exists_after`、`new_exists_before`、`new_exists_after`，以及 `sha256_before`、`sha256_after`。
- 按计划各写一行 `reference / reference_verified`，`path` 为引用文档，证据含 `old_href`、`new_href`、解析的 `target`、`target_sha256` 和文档的 `document_sha256_before`、`document_sha256_after`。
- 最后一行 `conflict / blocked_conflict`，`path` 为冲突源。证据含 `target`、`source_sha256`、`target_sha256`。失败按实测记录。

重扫 `work/` 全部文件保存 `records/after.json`，格式为 `{"entries":{"work/文件路径":{"sha256":"实测指纹","size":0,"mtime_ns":0}}}`，使用正斜杠，数值为实测整数。`records/run-notes.md` 记录工具、稳定链接验证、暂存和失败现场。
