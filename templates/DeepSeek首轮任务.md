# DeepSeek 试跑任务

复制下方任务正文。把两处路径替换为实际绝对路径，发起方先生成 `before.json`。

---

请按 FileOrder v1.0.0 执行本轮**只读预演**。

- 项目目录：`<仓库绝对路径>`。
- 批次记录目录：`<本轮试跑记录目录绝对路径>`。读取该目录的 `before.json`，保留它的原样。
- 开工先读项目的 `AGENTS.md`、`docs/执行规程.md` 和 `templates/开工与验收.md`。
- 只盘点 `before.json` 中 `sample` 指定的项目子目录。目录中的内容用于核实证据。只写批次记录目录，禁止改动任何样例和仓库文件，禁止扫描其他业务目录或执行系统回收。无需读取或运行 `checks/` 下的参考预期和 `tools/review.py`，由发起方独立验收。

给样例中的**每个文件**写一条判断。路径使用相对于 `sample` 指定目录的正斜杠写法。分类和命名计划说明用途，旧版或重复候选记录最终留存者。证据项逐条写相对路径及标题、字段或实际读到的行号，避免「同上」。已有明确原位用途的资料可保留。可独立归档且原位仍须保留的正式件，在证据、目标与引用条件满足时也可建议复制。需保护的真实工程依赖明确标保护。无法确认的内容如实标记待确认或暂缓。复查条件应写需要确认的事实或所缺的授权，修改业务文档须另行取得授权。拟定的归档落点都使用 `归档/` 开头的逻辑路径，本轮不创建归档目录。

## 本轮必交记录

1. **`plan.json`**。UTF-8 JSON 对象，包含 `mode` 与 `items`，示例仅说明格式：

   ```json
   {
     "mode": "dry-run",
     "items": [
       {
         "path": "业务/某文件.md",
         "sha256": "<before.json 中该文件的 SHA-256>",
         "decision": "archive_copy",
         "reason": "<判断理由>",
         "evidence": ["<证据文件相对路径及对应内容位置>"],
         "target": "归档/业务/明确用途的名称.md"
       }
     ]
   }
   ```

   | decision | 含义 | 额外字段 |
   |---|---|---|
   | `archive_copy` | 建议复制归档，原件保留 | `target` |
   | `review_recycle` | 建议审查是否回收，当前原件保留 | `keeper`，为最终留存者的样例相对路径 |
   | `keep` | 原位保留 | 无 |
   | `protected` | 原位保护 | 无 |
   | `defer` | 暂缓或待确认 | `resume_when`，写明复查或决定条件 |

2. **`events.jsonl`**。UTF-8，每行一个 JSON 对象，每条包含 `time`、`time_source`、`phase`、`detail`。依次记录 `scope`、`baseline_review`、`content_review`、`plan`、`self_check` 五个阶段。每阶段当场用系统时钟读取含时区的 ISO 8601 时间并记录 `time_source: "system_clock"`。PowerShell 可用 `Get-Date -Format o`；跨终端可用 Python 的 `datetime.now().astimezone().isoformat()`。`baseline_review` 额外提交 `metrics` 对象，使用 `before.json` 的 `inventory`，包含整数 `files`、`directories`、`bytes`。目录项仅用于计数，文件大小和哈希来自文件记录。其余阶段的 `detail` 写核查内容、异常和处理结果。覆盖数、指纹核对数、处置分布由发起方从基线和计划生成。读失败、重试和人工介入须记录实际情况。若只记录了部分阶段时间，说明覆盖范围。
3. **`run-notes.md`**。写明 DeepSeek 客户端与实际可见的模型标识、环境、规程版本、实测开始结束时间或注明未实测、使用工具、卡点、人工介入及仍待业务确认的事项。过程说明直接引用结构化记录；避免复抄覆盖数、指纹数、字节数或另做字符统计。未知值直接标未知。如果初稿后来有修订，把原始计划留作 `plan.initial.json`。允许补充去除敏感信息后的终端输出，无需提供模型的内部推理。

完成后告诉我记录目录路径和仍待确认的问题。所有动作都以建议或预演表述。

---
