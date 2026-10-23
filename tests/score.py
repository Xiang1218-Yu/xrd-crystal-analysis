#!/usr/bin/env python3
"""Turn a verified JUnit report into a normalized reward.

The scorer is intentionally small and fail-closed: missing tests, skipped
tests, pytest errors, malformed reports, and unexpected test IDs all result in
reward 0 and an INCOMPLETE status. Only a complete report with matching test
IDs can produce a non-zero reward.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _junit_case_id(node: ET.Element) -> str:
    classname = node.get("classname", "").strip()
    module = classname.split(".")[-1] + ".py" if classname else "test_xrd_analyzer.py"
    name = node.get("name", "").split("[", 1)[0]
    return f"{module}::{name}"


def write_outputs(args, *, reward: float, status: str, detail: dict) -> None:
    report = {
        "status": status,
        "reward": reward,
        **detail,
    }
    atomic_write(Path(args.report_out), json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n")
    atomic_write(Path(args.reward_out), f"{reward:.6f}\n")
    atomic_write(Path(args.status_out), status + "\n")


def load_config(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tests = payload.get("tests")
    if not isinstance(tests, dict) or not tests:
        raise ValueError("scoring config has no tests mapping")
    expected = {}
    for case_id, item in tests.items():
        if not isinstance(item, dict):
            raise ValueError(f"invalid scoring entry: {case_id}")
        weight = item.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ValueError(f"non-numeric weight: {case_id}")
        weight = float(weight)
        if not math.isfinite(weight) or weight <= 0.0 or weight > 1.0:
            raise ValueError(f"weight outside (0, 1]: {case_id}")
        if not str(item.get("rationale", "")).strip():
            raise ValueError(f"missing rationale: {case_id}")
        expected[case_id] = weight
    if abs(math.fsum(expected.values()) - 1.0) > 1e-9:
        raise ValueError("scoring weights do not sum to 1")
    gates = payload.get("gate_tests", [])
    if not isinstance(gates, list) or any(not isinstance(item, str) or not item for item in gates):
        raise ValueError("gate_tests must be a list of non-empty strings")
    return {"tests": expected, "gates": set(gates)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--junit", required=True)
    parser.add_argument("--report-out", required=True)
    parser.add_argument("--reward-out", required=True)
    parser.add_argument("--status-out", required=True)
    args = parser.parse_args()

    try:
        config = load_config(Path(args.config))
        tree = ET.parse(args.junit)
        root = tree.getroot()
        if root.tag not in {"testsuite", "testsuites"}:
            raise ValueError("JUnit root is not testsuite/testsuites")
        outcomes: dict[str, bool] = {}
        skipped: set[str] = set()
        errors = 0
        for node in root.iter("testcase"):
            case = _junit_case_id(node)
            if node.find("error") is not None:
                errors += 1
                outcomes[case] = False
            elif node.find("skipped") is not None:
                skipped.add(case)
                outcomes[case] = False
            elif node.find("failure") is not None:
                outcomes[case] = False
            else:
                outcomes.setdefault(case, True)

        expected = set(config["tests"]) | config["gates"]
        missing = sorted(expected - set(outcomes))
        unexpected = sorted(set(outcomes) - expected)
        if skipped or errors or missing or unexpected:
            detail = {
                "test_count": len(outcomes),
                "expected_count": len(expected),
                "missing": missing,
                "unexpected": unexpected,
                "skipped": sorted(skipped),
                "errors": errors,
            }
            write_outputs(args, reward=0.0, status="INCOMPLETE", detail=detail)
            return 2

        gate_passed = all(outcomes.get(case, False) for case in config["gates"])
        passed = [case for case, ok in outcomes.items() if ok]
        if not gate_passed:
            reward = 0.0
        else:
            reward = math.fsum(config["tests"][case] for case in passed if case in config["tests"])
            reward = round(reward, 6)
        write_outputs(
            args,
            reward=reward,
            status="COMPLETED",
            detail={
                "test_count": len(outcomes),
                "passed_count": len(passed),
                "failed_count": len(expected) - len(passed),
                "gate_passed": gate_passed,
            },
        )
        return 0
    except Exception as exc:
        try:
            write_outputs(args, reward=0.0, status="INCOMPLETE", detail={"error": str(exc)})
            atomic_write(Path(args.reward_out), "0.000000\n")
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
