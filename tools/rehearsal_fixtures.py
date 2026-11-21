"""Synthetic fixtures and explicit operation plans for the Windows exercises."""

from hashlib import sha256


def scenario_data(scenario):
    if scenario == "copy":
        sources = {
            "work/输入/final.md": "# 社区活动执行方案\n\n已验收。包含报名、分组、签到。\n",
            "work/输入/交付纪要.md": "# 活动交付纪要\n\n活动资料已交付，复盘待负责人确认。\n",
        }
        copies = [
            {"source": "work/输入/final.md", "target": "work/归档/社区活动执行方案.md"},
            {"source": "work/输入/交付纪要.md", "target": "work/归档/交付纪要.md"},
        ]
        conflict = {"source": copies[0]["source"], "target": "work/冲突/社区活动执行方案.md"}
        texts = sources | {conflict["target"]: "# 既有执行方案\n\n这是一份独立资料。\n"}
        return texts, {"copies": copies, "conflict": conflict}, ("work/归档",)
    if scenario == "rename":
        source = "work/交付/final.md"
        target = "work/交付/社区活动执行方案.md"
        conflicts = {"source": "work/冲突/old.md", "target": "work/冲突/活动交接.md"}
        texts = {
            source: "# 社区活动执行方案\n\n已验收的演练成果。\n",
            "work/README.md": "# 交付入口\n\n查看[执行方案](./交付/final.md)。\n\n历史原名为 `final.md`。\n",
            "work/记录/索引.md": "# 交付索引\n\n[执行方案](../交付/final.md)\n[说明](../交付/说明.md)\n\n历史路径为 `../交付/final.md`。\n",
            "work/交付/说明.md": "# 稳定链接目标\n\n归档说明。\n",
            conflicts["source"]: "# 待改名的交接记录\n",
            conflicts["target"]: "# 已有同名交接记录\n",
            "work/冲突/索引.md": "# 冲突样例入口\n\n[交接记录](./old.md)\n",
        }
        links = [
            {"document": "work/README.md", "old_href": "./交付/final.md",
             "new_href": "./交付/社区活动执行方案.md"},
            {"document": "work/记录/索引.md", "old_href": "../交付/final.md",
             "new_href": "../交付/社区活动执行方案.md"},
        ]
        stable_links = [
            {"document": "work/记录/索引.md", "href": "../交付/说明.md",
             "target": "work/交付/说明.md"},
            {"document": "work/冲突/索引.md", "href": "./old.md",
             "target": conflicts["source"]},
        ]
        return texts, {"source": source, "target": target, "reference_edits": links,
                       "stable_links": stable_links, "conflict": conflicts}, ()
    if scenario == "recycle":
        sample = "work/样例/回收恢复试验.txt"
        return {sample: "Windows 回收和还原试验用的虚构文本。\n没有业务资料。\n"}, {
            "sample": sample, "restore_to": sample,
        }, ()
    raise ValueError(f"未知场景：{scenario}")


def expected_file(text):
    content = text.encode("utf-8")
    return {"size": len(content), "sha256": sha256(content).hexdigest()}
