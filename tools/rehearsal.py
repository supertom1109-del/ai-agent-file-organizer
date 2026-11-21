"""Prepare and independently check isolated execution exercises. Performs no file operations under test."""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
import json
import re
import stat
import subprocess
import sys

from rehearsal_fixtures import expected_file, scenario_data
from review import ROOT, load_json, snapshot_tree, write_json


SCENARIOS = ("copy", "rename", "recycle")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def plain_file(path):
    info = path.lstat()
    need(stat.S_ISREG(info.st_mode) and not (
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    ), f"预期普通文件：{path}")
    return path


def inputs(run):
    baseline = load_json(plain_file(run / "before.json"))
    plan = load_json(plain_file(run / "plan.json"))
    scenario = baseline["scenario"]
    fixtures, expected_plan, directories = scenario_data(scenario)
    need(baseline["schema"] == 1 and plan == {"scenario": scenario, **expected_plan},
         "期初清单或操作计划与发布样例不一致")
    files = baseline["entries"]
    need(set(files) == set(fixtures), "期初文件列表缺项或超范围")
    for path, text in fixtures.items():
        need(all(files[path].get(key) == value for key, value in expected_file(text).items()),
             f"期初文件与发布样例不一致：{path}")
    parents = {parent.as_posix() for path in fixtures for parent in PurePosixPath(path).parents
               if parent.as_posix() not in (".", "work")}
    return baseline, plan, fixtures, parents | set(directories)


def snapshot_work(run):
    observed = {"work/" + name: item for name, item in snapshot_tree(run / "work").items()}
    directories = {path for path, entry in observed.items() if entry["type"] == "directory"}
    files = {path: {key: value for key, value in entry.items() if key != "type"}
             for path, entry in observed.items() if entry["type"] == "file"}
    return files, directories


def prepare(run, scenario):
    texts, plan, directories = scenario_data(scenario)
    run.mkdir(parents=True, exist_ok=False)
    for name in directories:
        (run / name).mkdir(parents=True)
    (run / "records").mkdir()
    for name, text in texts.items():
        path = run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    files, _ = snapshot_work(run)
    write_json(run / "before.json", {"schema": 1, "scenario": scenario,
                                    "captured_at": datetime.now().astimezone().isoformat(), "entries": files})
    write_json(run / "plan.json", {"scenario": scenario, **plan})
    guide = (ROOT / "templates" / f"执行试跑_{scenario}.md").read_text(encoding="utf-8")
    guide = guide.replace("{批次目录}", str(run)).replace("{工具目录}", str(ROOT / "tools"))
    (run / "任务.md").write_text(guide, encoding="utf-8", newline="\n")
    print(f"已准备隔离样例：{run / '任务.md'}")


def load_operations(path, since):
    upper = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) + timedelta(seconds=2)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()]
    need(since.utcoffset() is not None, "期初采集时间缺少时区")
    for row in rows:
        at = datetime.fromisoformat(row["time"])
        need(at.utcoffset() is not None and since <= at <= upper, "动作时间无时区、顺序错误或超出观测区间")
        need(isinstance(row["evidence"], dict), "动作缺少结构化证据")
        since = at
    return rows


def require_rows(ops, steps):
    need([(row["phase"], row["path"], row["result"]) for row in ops] == steps,
         "动作阶段、路径、状态或条数与计划不一致")


def check_copy(records, plan, before, after, ops):
    copies = plan["copies"]
    conflict = plan["conflict"]
    targets = {item["target"] for item in copies}
    need(set(after) == set(before) | targets, "复制批次出现缺失或额外文件")
    need(all(after[path] == state for path, state in before.items()), "原件或既有冲突文件变化")
    for item in copies:
        source, target = before[item["source"]], after[item["target"]]
        need(all(source[key] == target[key] for key in ("sha256", "size")), "归档副本与原件不一致")
    archive = {path: after[path] for path in targets}
    for filename in ("copy-first.json", "copy-repeat.json"):
        need(load_json(plain_file(records / filename))["entries"] == archive, f"目标快照与期末实物不一致：{filename}")

    steps = [("normal", "copied_verified", item) for item in copies]
    steps += [("repeat", "skipped_same_content", item) for item in copies]
    steps.append(("conflict", "blocked_conflict", conflict))
    require_rows(ops, [(phase, item["source"], result) for phase, result, item in steps])
    for row, (_, _, item) in zip(ops, steps, strict=True):
        evidence = row["evidence"]
        need((evidence.get("target"), evidence.get("source_sha256"), evidence.get("target_sha256")) == (
            item["target"], before[item["source"]]["sha256"], after[item["target"]]["sha256"]
        ), "复制或冲突日志与实物不一致")
    need(before[conflict["source"]]["sha256"] != before[conflict["target"]]["sha256"],
         "冲突样例必须不同内容")
    return {"verified_copies": len(copies), "repeated_skips": len(copies), "protected_conflicts": 1}


def check_rename(run, plan, fixtures, before, after, ops):
    source, target = plan["source"], plan["target"]
    edits = plan["reference_edits"]
    conflict = plan["conflict"]
    need(set(after) == (set(before) - {source}) | {target}, "旧路径仍在、目标缺失或出现额外文件")
    need(all(after[target][field] == before[source][field] for field in ("sha256", "size")),
         "改名后的内容指纹或大小已改变")
    edit_paths = {edit["document"] for edit in edits}
    need(all(after[path] == before[path] for path in set(before) - {source} - edit_paths),
         "稳定文件或冲突文件被修改")
    require_rows(ops, [("rename", target, "renamed_verified"),
                       *[("reference", edit["document"], "reference_verified") for edit in edits],
                       ("conflict", conflict["source"], "blocked_conflict")])
    rename = ops[0]["evidence"]
    for field, value in (("old_exists_before", True), ("old_exists_after", False),
                         ("new_exists_before", False), ("new_exists_after", True)):
        need(rename.get(field) is value, f"改名状态与实物矛盾：{field}")
    need(rename.get("old_path") == source and rename.get("sha256_before") == before[source]["sha256"]
         and rename.get("sha256_after") == after[target]["sha256"], "改名日志路径或指纹不匹配")
    for edit, row in zip(edits, ops[1:-1], strict=True):
        path = edit["document"]
        old, new = edit["old_href"], edit["new_href"]
        marker = f"]({old})"
        original = fixtures[path]
        need(original.count(marker) == 1, "授权链接无法唯一匹配")
        required = original.replace(marker, f"]({new})", 1)
        need((run / path).read_bytes() == required.encode("utf-8"), f"引用文档含未经授权的差异：{path}")
        resolved = (run / path).parent.joinpath(new).resolve(strict=True)
        need(resolved == run / target and resolved.read_bytes(), "修复后链接无法读取计划目标")
        evidence = row["evidence"]
        need((evidence.get("old_href"), evidence.get("new_href"), evidence.get("target"),
              evidence.get("target_sha256"), evidence.get("document_sha256_before"),
              evidence.get("document_sha256_after")) ==
             (old, new, target, after[target]["sha256"], before[path]["sha256"], after[path]["sha256"]),
             f"引用更新日志与实物不一致：{path}")
    for link in plan["stable_links"]:
        document = run / link["document"]
        resolved = document.parent.joinpath(link["href"]).resolve(strict=True)
        need(f"]({link['href']})" in document.read_text(encoding="utf-8")
             and resolved == run / link["target"] and resolved.read_bytes(), "稳定链接已失效")
    protected = ops[-1]["evidence"]
    need((protected.get("target"), protected.get("source_sha256"), protected.get("target_sha256")) ==
         (conflict["target"], before[conflict["source"]]["sha256"], before[conflict["target"]]["sha256"]),
         "冲突日志与实物不一致")
    return {"verified_renames": 1, "repaired_links": len(edits),
            "stable_links": len(plan["stable_links"]), "protected_conflicts": 1}


def check_recycle(run, records, plan, before, after, ops):
    from windows_recycle import current_user_bin, parse_metadata, usable_capacity

    sample = plan["sample"]
    source = run / sample
    start, restored = before[sample], after.get(sample)
    need(restored == start and set(after) == {sample}, "原测试路径未恢复或与期初状态不一致")
    require_rows(ops, [(phase, sample, result) for phase, result in (
        ("quota", "preflight_passed"), ("before_recycle", "sampled"),
        ("after_recycle", "recycled_verified"), ("after_restore", "restored_verified"),
    )])
    quota = load_json(plain_file(records / "quota.json"))
    passed, headroom = usable_capacity(quota["configured_quota_mb"], quota["nuke_on_delete"],
                                       quota["current_usage_bytes"], start["size"])
    need(passed and quota.get("capacity_check_passed") is True and quota.get("quota_is_estimate") is False
         and quota["conservative_headroom_bytes"] == headroom
         and quota["sample"] == sample and quota["sample_sha256"] == start["sha256"]
         and quota["source_volume"] == source.drive and quota["checked_at"] == ops[0]["time"],
         "缺少动作前的实际配额证据、容量不足或证据对象错误")
    need(datetime.fromisoformat(ops[0]["time"]) < datetime.fromisoformat(ops[1]["time"]),
         "配额检查必须发生在回收动作前")
    need(ops[1]["evidence"].get("exists_before") is True, "缺少原测试路径的回收前实测")
    recycled, recovery = (row["evidence"] for row in ops[2:])
    meta = plain_file(records / "recycle-index.bin").read_bytes()
    original, size, at = parse_metadata(meta)
    need(PureWindowsPath(original) == PureWindowsPath(source) and size == start["size"]
         and datetime.fromisoformat(ops[1]["time"]) <= at <= datetime.fromisoformat(ops[2]["time"]),
         "系统回收索引的原路径、大小或时间与本批动作不符")
    index, entity = recycled["index_name"], recycled["entity_name"]
    need(re.fullmatch(r"\$I[A-Za-z0-9]+\.txt", index) and entity == "$R" + index[2:],
         "回收索引与内容实体的名称未正确配对")
    need(recycled.get("exists_after") is False and recycled.get("entity_sha256") == start["sha256"]
         and recycled.get("entity_size") == start["size"], "回收后的实际内容证据不完整")
    need(recovery.get("exists_after") is True and recovery.get("shell_entry_count_after") == 0
         and recovery.get("restored_sha256") == start["sha256"]
         and recovery.get("restored_size") == start["size"],
         "恢复日志与原位实物不一致")
    bin_root = current_user_bin(source.anchor)
    need(not (bin_root / entity).exists(), "本批内容实体仍留在回收站")
    index_path = bin_root / index
    residual = index_path.exists()
    if residual:
        need(plain_file(index_path).read_bytes() == meta, "残留索引与本批留档不匹配")
    return {"recycled_verified": 1, "restored_verified": 1, "index_only_residual": residual}


def capacity(run):
    baseline, plan, _, _ = inputs(run)
    need(plan["scenario"] == "recycle", "只有系统回收样例需要核对配额")
    from windows_recycle import read_capacity

    sample = run / plan["sample"]
    states, _ = snapshot_work(run)
    need(states == baseline["entries"], "回收样例与期初状态不一致")
    checked_at = datetime.now().astimezone().isoformat()
    result = read_capacity(sample.anchor, sample.stat().st_size)
    result.update(sample=plan["sample"], sample_sha256=states[plan["sample"]]["sha256"], checked_at=checked_at)
    records = run / "records"
    need(records.is_dir() and records.resolve() == records, "记录目录不得指向隔离区之外")
    write_json(records / "quota.json", result)
    print("配额核验通过。" if result["capacity_check_passed"] else "配额不足或配置不允许回收。")
    return 0 if result["capacity_check_passed"] else 1


def check(run):
    result = {"passed": False, "scenario": None}
    try:
        baseline, plan, fixtures, expected_dirs = inputs(run)
        scenario = result["scenario"] = plan["scenario"]
        before = baseline["entries"]
        after, dirs = snapshot_work(run)
        need(dirs == expected_dirs, "工作目录中出现未授权目录或缺失目录")
        records = run / "records"
        need(records.is_dir() and records.resolve() == records, "记录目录不得指向隔离区之外")
        ops = load_operations(plain_file(records / "ops.jsonl"), datetime.fromisoformat(baseline["captured_at"]))
        need(load_json(plain_file(records / "after.json"))["entries"] == after,
             "执行方期末快照与磁盘实物不一致")
        need(bool(plain_file(records / "run-notes.md").read_text(encoding="utf-8-sig").strip()),
             "缺少执行说明")
        if scenario == "copy":
            result["counts"] = check_copy(records, plan, before, after, ops)
        elif scenario == "rename":
            result["counts"] = check_rename(run, plan, fixtures, before, after, ops)
        else:
            result["counts"] = check_recycle(run, records, plan, before, after, ops)
        result["passed"] = True
    except (AttributeError, ImportError, KeyError, OSError, TypeError, ValueError, OverflowError,
            subprocess.SubprocessError) as error:
        result["error"] = str(error)
    write_json(run / "check.json", result)
    print(f"检查{'通过' if result['passed'] else '未通过'}，结果在 {run / 'check.json'}")
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "capacity", "check"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--run", type=Path, required=True)
        if command == "prepare":
            subparser.add_argument("scenario", choices=SCENARIOS)
    args = parser.parse_args()
    run = args.run.resolve()
    try:
        need(run != ROOT and not run.is_relative_to(ROOT), "批次目录必须在仓库之外")
        if args.command == "prepare":
            prepare(run, args.scenario)
            return 0
        if args.command == "capacity":
            return capacity(run)
        need((run / "before.json").is_file() and (run / "plan.json").is_file(), "请指定本工具准备的隔离批次")
        need(not (run / "check.json").exists(), "已存在验收结果，请保留原记录，另开批次")
        return check(run)
    except (ImportError, KeyError, OSError, TypeError, ValueError, subprocess.SubprocessError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
