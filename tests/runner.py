#!/usr/bin/env python3
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1])
script = root / "src" / "xrd_analyzer.py"
WAVELENGTH = 1.5406
HKLS = [[1, 1, 1], [2, 0, 0], [2, 2, 0], [3, 1, 1], [2, 2, 2], [4, 0, 0]]


def norm(hkl):
    return sum(value * value for value in hkl)


def forward_two_theta(lattice, hkl, shift, wavelength=WAVELENGTH):
    ratio = wavelength * math.sqrt(norm(hkl)) / (2.0 * lattice)
    return math.degrees(2.0 * math.asin(ratio)) + shift


def make_payload(lattice=3.61, shift=0.18, unit="angstrom", wavelength=WAVELENGTH, include_outliers=()):
    if unit == "nm":
        wavelength = wavelength / 10.0
    elif unit == "pm":
        wavelength = wavelength * 100.0
    ordered = [("p111", [1, 1, 1]), ("p200", [2, 0, 0]), ("p220", [2, 2, 0]), ("p311", [3, 1, 1])]
    peaks = [
        {"id": peak_id, "two_theta_deg": round(forward_two_theta(lattice, hkl, shift), 5), "intensity": 100.0 - index * 17.0}
        for index, (peak_id, hkl) in enumerate(ordered)
    ]
    peaks.extend(include_outliers)
    return {
        "crystal_system": "cubic",
        "wavelength": {"value": wavelength, "unit": unit},
        "candidate_hkls": HKLS,
        "lattice_parameter_bounds_angstrom": [3.45, 3.78],
        "zero_shift_bounds_deg": [-0.35, 0.35],
        "peak_position_tolerance_deg": 0.075,
        "outlier_tolerance": 0.08,
        "peaks": peaks,
    }


def run(payload):
    with tempfile.TemporaryDirectory() as td:
        inp = Path(td) / "in.json"
        out = Path(td) / "out.json"
        inp.write_text(json.dumps(payload))
        process = subprocess.run([sys.executable, str(script), "--input", str(inp), "--output", str(out)], capture_output=True, text=True)
        if process.returncode != 0:
            raise RuntimeError(process.stderr)
        return json.loads(out.read_text())


def by_id(result):
    return {row["id"]: row for row in result["peaks"]}


def check_shape(result, payload):
    if result.get("crystal_system") != "cubic" or len(result.get("peaks", [])) != len(payload["peaks"]):
        return False
    expected = {"id", "intensity", "d_spacing_angstrom", "assigned_hkl", "lattice_parameter_angstrom", "residual_angstrom", "predicted_two_theta_deg", "two_theta_residual_deg", "anomalous"}
    return all(expected <= set(row) for row in result["peaks"])


def check_group1():
    payload = make_payload(lattice=3.61, shift=0.18)
    result = run(payload)
    expected = {"p111": [1, 1, 1], "p200": [2, 0, 0], "p220": [2, 2, 0], "p311": [3, 1, 1]}
    if not check_shape(result, payload):
        return False
    if abs(result["lattice_parameter_angstrom"] - 3.61) > 0.015 or abs(result["zero_shift_two_theta_deg"] - 0.18) > 0.015:
        return False
    rows = by_id(result)
    return all(rows[peak_id]["assigned_hkl"] == hkl and not rows[peak_id]["anomalous"] and rows[peak_id]["two_theta_residual_deg"] < 0.02 for peak_id, hkl in expected.items())


def check_group2():
    results = [run(make_payload(lattice=3.67, shift=-0.23, unit=unit)) for unit in ("angstrom", "nm", "pm")]
    reference = results[0]
    if abs(reference["lattice_parameter_angstrom"] - 3.67) > 0.015 or abs(reference["zero_shift_two_theta_deg"] + 0.23) > 0.015:
        return False
    return all(
        abs(result["lattice_parameter_angstrom"] - reference["lattice_parameter_angstrom"]) < 1e-6
        and abs(result["zero_shift_two_theta_deg"] - reference["zero_shift_two_theta_deg"]) < 1e-6
        and [row["assigned_hkl"] for row in result["peaks"]] == [row["assigned_hkl"] for row in reference["peaks"]]
        for result in results[1:]
    )


def check_group3():
    # Several candidate planes can locally explain an individual peak; a common
    # lattice/shift must explain all recorded inlier peaks simultaneously.
    payload = make_payload(lattice=3.735, shift=0.31)
    payload["lattice_parameter_bounds_angstrom"] = [3.60, 3.80]
    payload["zero_shift_bounds_deg"] = [-0.35, 0.35]
    result = run(payload)
    rows = by_id(result)
    return (
        abs(result["lattice_parameter_angstrom"] - 3.735) < 0.018
        and abs(result["zero_shift_two_theta_deg"] - 0.31) < 0.018
        and rows["p111"]["assigned_hkl"] == [1, 1, 1]
        and rows["p311"]["assigned_hkl"] == [3, 1, 1]
        and result["anomalous_peak_ids"] == []
    )


def check_group4():
    outliers = [
        {"id": "bad-low", "two_theta_deg": 56.173, "intensity": 4.0},
        {"id": "bad-high", "two_theta_deg": 96.409, "intensity": 3.0},
    ]
    payload = make_payload(lattice=3.58, shift=-0.16, include_outliers=outliers)
    result = run(payload)
    rows = by_id(result)
    return (
        abs(result["lattice_parameter_angstrom"] - 3.58) < 0.018
        and abs(result["zero_shift_two_theta_deg"] + 0.16) < 0.018
        and result["anomalous_peak_ids"] == ["bad-low", "bad-high"]
        and all(rows[peak_id]["anomalous"] and rows[peak_id]["two_theta_residual_deg"] > payload["peak_position_tolerance_deg"] for peak_id in ("bad-low", "bad-high"))
        and all(not rows[peak_id]["anomalous"] for peak_id in ("p111", "p200", "p220", "p311"))
    )


checks = [check_group1, check_group2, check_group3, check_group4]
for index, check in enumerate(checks, 1):
    try:
        value = 1 if check() else 0
    except Exception as exc:
        print(f"GROUP{index}=0")
        print(f"GROUP{index}_ERROR={exc}")
        continue
    print(f"GROUP{index}={value}")
