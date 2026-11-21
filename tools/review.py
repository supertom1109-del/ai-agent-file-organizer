"""Capture and verify a read-only rehearsal of the bundled sample folder."""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
VERSION = "v1.0.0"
SAMPLES = {"inbox": "expected.json", "holdout": "holdout-expected.json"}
PHASES = ("scope", "baseline_review", "content_review", "plan", "self_check")


def snapshot_tree(sample_root):
    entries = {}

    def visit(path):
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError(f"样例含链接或重解析点：{path}")
        if stat.S_ISDIR(info.st_mode):
            if path != sample_root:
                entries[path.relative_to(sample_root).as_posix()] = {"type": "directory"}
            for child in sorted(path.iterdir()):
                visit(child)
        elif stat.S_ISREG(info.st_mode):
            digest = sha256(path.read_bytes()).hexdigest()
            current = path.stat()
            if (info.st_size, info.st_mtime_ns) != (current.st_size, current.st_mtime_ns):
                raise ValueError(f"读取过程中样例变化：{path}")
            entries[path.relative_to(sample_root).as_posix()] = {
                "type": "file", "size": info.st_size,
                "mtime_ns": info.st_mtime_ns, "sha256": digest,
            }
        else:
            raise ValueError(f"样例中包含不支持的对象：{path}")

    visit(sample_root)
    return entries


def snapshot(sample):
    return {"sample": f"examples/{sample}", "entries": snapshot_tree(ROOT / "examples" / sample)}


def inventory(entries):
    files = [entry for entry in entries.values() if entry["type"] == "file"]
    return {"files": len(files), "directories": len(entries) - len(files),
            "bytes": sum(entry["size"] for entry in files)}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, value):
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


def text_value(value):
    return isinstance(value, str) and bool(value.strip())


def target_key(value):
    if not text_value(value) or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.as_posix() != value or len(path.parts) < 2 or path.parts[0] != "归档":
        return None
    for part in path.parts:
        if (
            part == ".." or part.endswith((" ", ".")) or PureWindowsPath(part).is_reserved()
            or any(char in '<>:"|?*' or ord(char) < 32 for char in part)
        ):
            return None
    return unicodedata.normalize("NFC", value).casefold()


def check_plan(plan, expected, entries):
    if not isinstance(plan, dict) or plan.get("mode") != "dry-run":
        raise ValueError('plan.json 必须为 JSON 对象，mode 必须为 "dry-run"')
    if not isinstance(plan.get("items"), list):
        raise ValueError("plan.json 缺少 items 数组")

    targets = {}
    decisions = {}
    verified = 0
    errors = []
    for item in plan["items"]:
        if not isinstance(item, dict) or not text_value(item.get("path")):
            errors.append("判断条目缺少路径")
            continue
        path = item["path"]
        if path in decisions or path not in expected:
            errors.append(f"重复或范围外条目：{path}")
            continue
        decision = item.get("decision")
        decisions[path] = decision
        rule = expected[path]
        if item.get("sha256") == entries[path]["sha256"]:
            verified += 1
        else:
            errors.append(f"基线指纹不一致：{path}")
        accepted = (rule["decision"], *rule.get("alternatives", []))
        if decision not in accepted:
            errors.append(f"判断与样例预期不一致：{path}，预期 {' / '.join(accepted)}")
        evidence = item.get("evidence")
        if not text_value(item.get("reason")) or (
            not isinstance(evidence, list) or not evidence or not all(map(text_value, evidence))
        ):
            errors.append(f"缺少理由或证据：{path}")
        if decision == "archive_copy":
            target = target_key(item.get("target"))
            if target is None:
                errors.append(f"目标路径非法：{path}")
            else:
                if not all(term.casefold() in target.replace(" ", "")
                           for term in rule.get("target_terms", [])):
                    errors.append(f"归档路径缺少主题或版本依据：{path}")
                for existing, owner in targets.items():
                    if (
                        existing == target or existing.startswith(target + "/")
                        or target.startswith(existing + "/")
                    ):
                        errors.append(f"归档落点冲突：{owner}、{path}")
                targets[target] = path
        if decision == "review_recycle":
            keeper = item.get("keeper")
            if not text_value(keeper) or keeper == path or keeper not in expected or keeper != rule.get("keeper"):
                errors.append(f"最终留存者有误：{path}")
            elif rule.get("same_content") and entries[path]["sha256"] != entries[keeper]["sha256"]:
                errors.append(f"重复回收候选与留存者指纹不同：{path}")
        if decision == "defer" and not text_value(item.get("resume_when")):
            errors.append(f"缺少复查条件：{path}")

    for path, decision in decisions.items():
        if decision == "review_recycle":
            keeper = expected[path].get("keeper")
            if decisions.get(keeper) not in ("keep", "protected", "archive_copy"):
                errors.append(f"最终留存者未获保留判断：{path}")
    errors.extend(f"计划漏项：{path}" for path in sorted(expected.keys() - decisions.keys()))
    status_counts = Counter(decision for decision in decisions.values() if decision in (
        "archive_copy", "defer", "keep", "protected", "review_recycle",
    ))
    summary = {"planned": len(decisions), "fingerprints_verified": verified,
               "decisions": dict(sorted(status_counts.items()))}
    return summary, errors


def check_events(path, counts, captured_at):
    phases = []
    previous = None
    last_write = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) + timedelta(seconds=2)
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        event = json.loads(line)
        if not isinstance(event, dict) or not all(
            text_value(event.get(key)) for key in ("time", "phase", "detail")
        ):
            raise ValueError("events.jsonl 有字段缺失")
        current = datetime.fromisoformat(event["time"])
        if current.utcoffset() is None or (previous is not None and current < previous):
            raise ValueError("事件时间须包含时区且按时间顺序排列")
        previous = current
        phase = event["phase"]
        if captured_at is not None:
            if event.get("time_source") != "system_clock" or not captured_at <= current <= last_write:
                raise ValueError("事件时间缺少系统时钟来源或超出基线采集至日志落盘的区间")
            if phase == "baseline_review" and counts is not None:
                metrics = event.get("metrics")
                if not isinstance(metrics, dict) or any(
                    type(metrics.get(key)) is not int or metrics[key] != value
                    for key, value in counts.items()
                ):
                    raise ValueError(f"事件中的基线统计与实测不一致，实际为 {counts}")
        if phase in PHASES and (not phases or phases[-1] != phase):
            phases.append(phase)
    if tuple(phases) != PHASES:
        raise ValueError("events.jsonl 缺少规定阶段或阶段顺序错误")


def review(run):
    for name in ("after.json", "check.json"):
        if (run / name).exists():
            raise ValueError(f"{name} 已存在。后续试跑请使用新的批次目录。")

    expected = {}
    errors = []
    plan_summary = {"planned": 0, "fingerprints_verified": 0, "decisions": {}}
    changes = None
    counts = None
    captured_at = None
    protocol = None
    try:
        baseline = load_json(run / "before.json")
        sample = baseline["sample"].removeprefix("examples/")
        if sample not in SAMPLES or baseline["sample"] != f"examples/{sample}":
            raise ValueError("未知的样例目录")
        protocol = baseline.get("protocol_version")
        if protocol is not None:
            captured_at = datetime.fromisoformat(baseline["captured_at"])
            if captured_at.utcoffset() is None:
                raise ValueError("基线采集时间缺少时区")
        expected = load_json(ROOT / "checks" / SAMPLES[sample])
        before = baseline["entries"]
        counts = inventory(before)
        after = snapshot(sample)
        write_json(run / "after.json", after)
        actual = after["entries"]
        changes = {
            "added": sorted(actual.keys() - before.keys()),
            "missing": sorted(before.keys() - actual.keys()),
            "changed": sorted(path for path in before.keys() & actual.keys()
                              if before[path] != actual[path]),
        }
        if any(changes.values()):
            errors.append("样例在预演前后发生变化")
        if set(expected) != {path for path, entry in before.items() if entry["type"] == "file"}:
            errors.append("基线文件集合与样例清单不一致")
        else:
            plan_summary, plan_errors = check_plan(load_json(run / "plan.json"), expected, before)
            errors.extend(plan_errors)
    except (AttributeError, ValueError, OSError, KeyError, TypeError) as error:
        errors.append(f"基线、样例或计划校验失败：{error}")

    try:
        check_events(run / "events.jsonl", counts, captured_at)
        if not (run / "run-notes.md").read_text(encoding="utf-8-sig").strip():
            errors.append("run-notes.md 为空")
    except (ValueError, OSError, TypeError) as error:
        errors.append(f"试跑记录校验失败：{error}")

    write_json(run / "check.json", {
        "passed": not errors,
        "reviewer_version": VERSION,
        "baseline_protocol": protocol or "legacy",
        "inventory": counts,
        "coverage": {"expected": len(expected), "planned": plan_summary["planned"]},
        "fingerprints": {"expected": len(expected), "verified": plan_summary["fingerprints_verified"]},
        "decisions": plan_summary["decisions"],
        "sample_changes": changes,
        "errors": errors,
    })
    print(f"检查{'通过' if not errors else '未通过'}。查看 {run / 'check.json'}")
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("before", "check"))
    parser.add_argument("--run", type=Path, required=True, help="独立的批次记录目录")
    parser.add_argument("--sample", choices=SAMPLES, help="仅用于建立基线，默认 inbox")
    args = parser.parse_args()
    run = args.run.resolve()
    try:
        if run.is_relative_to(ROOT):
            raise ValueError("批次记录目录应放在仓库外")
        if args.command == "before":
            state = snapshot(args.sample or "inbox")
            state["protocol_version"] = VERSION
            state["captured_at"] = datetime.now().astimezone().isoformat()
            state["inventory"] = inventory(state["entries"])
            run.mkdir(parents=True, exist_ok=False)
            write_json(run / "before.json", state)
            print(f"已保存基线。样例范围：{state['sample']}，批次记录目录：{run}")
            return 0
        if args.sample is not None:
            raise ValueError("验收时使用基线中的样例目录，无需指定 --sample")
        return review(run)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
