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
ALLOWED = [[1, 1, 1], [2, 0, 0], [2, 2, 0], [3, 1, 1], [2, 2, 2], [4, 0, 0]]
FORBIDDEN = [[1, 0, 0], [2, 1, 1], [2, 2, 1]]


def norm(hkl):
    return sum(value * value for value in hkl)


def forward(lattice, hkl, shift):
    return math.degrees(2.0 * math.asin(WAVELENGTH * math.sqrt(norm(hkl)) / (2.0 * lattice))) + shift


def size_nm(fwhm_deg, instrument_deg, two_theta_deg, shift, shape_factor=0.9):
    beta = math.sqrt(math.radians(fwhm_deg) ** 2 - math.radians(instrument_deg) ** 2)
    theta = math.radians((two_theta_deg - shift) / 2.0)
    return shape_factor * WAVELENGTH / (beta * math.cos(theta)) / 10.0


def payload(lattice=3.61, shift=0.18, unit="angstrom", fwhms=(0.30, 0.31, 0.34, 0.39), extras=()):
    wavelength = {"angstrom": WAVELENGTH, "nm": WAVELENGTH / 10.0, "pm": WAVELENGTH * 100.0}[unit]
    indexed = [("p111", [1, 1, 1]), ("p200", [2, 0, 0]), ("p220", [2, 2, 0]), ("p311", [3, 1, 1])]
    peaks = [{"id": name, "two_theta_deg": round(forward(lattice, hkl, shift), 5), "fwhm_deg": fwhms[index], "intensity": 100.0 - 15.0 * index} for index, (name, hkl) in enumerate(indexed)]
    peaks.extend(extras)
    return {"crystal_system": "cubic", "structure": "fcc", "wavelength": {"value": wavelength, "unit": unit}, "candidate_hkls": ALLOWED + FORBIDDEN, "lattice_parameter_bounds_angstrom": [3.45, 3.78], "zero_shift_bounds_deg": [-0.35, 0.35], "peak_position_tolerance_deg": 0.075, "instrument_fwhm_deg": 0.12, "shape_factor": 0.9, "outlier_tolerance": 0.08, "peaks": peaks}


def run(data):
    with tempfile.TemporaryDirectory() as directory:
        source, output = Path(directory) / "in.json", Path(directory) / "out.json"
        source.write_text(json.dumps(data))
        process = subprocess.run([sys.executable, str(script), "--input", str(source), "--output", str(output)], capture_output=True, text=True)
        if process.returncode:
            raise RuntimeError(process.stderr)
        return json.loads(output.read_text())


def rows(result):
    return {row["id"]: row for row in result["peaks"]}


def check_shape(result, data):
    fields = {"id", "intensity", "fwhm_deg", "d_spacing_angstrom", "assigned_hkl", "lattice_parameter_angstrom", "residual_angstrom", "predicted_two_theta_deg", "two_theta_residual_deg", "corrected_fwhm_deg", "crystallite_size_nm", "anomalous"}
    return result.get("crystal_system") == "cubic" and result.get("structure") == "fcc" and len(result.get("peaks", [])) == len(data["peaks"]) and all(fields <= set(row) for row in result["peaks"])


def check_group1():
    data = payload(lattice=3.61, shift=0.18)
    result = run(data)
    indexed = {"p111": [1, 1, 1], "p200": [2, 0, 0], "p220": [2, 2, 0], "p311": [3, 1, 1]}
    table = rows(result)
    return check_shape(result, data) and abs(result["lattice_parameter_angstrom"] - 3.61) < 0.015 and abs(result["zero_shift_two_theta_deg"] - 0.18) < 0.015 and result["anomalous_peak_ids"] == [] and all(table[name]["assigned_hkl"] == hkl and not table[name]["anomalous"] and table[name]["two_theta_residual_deg"] < 0.02 for name, hkl in indexed.items())


def check_group2():
    # Forbidden planes have positions that can be locally tempting; only FCC-allowed
    # assignments may support the common main-phase model.
    data = payload(lattice=3.735, shift=-0.27)
    result = run(data)
    table = rows(result)
    forbidden = {tuple(hkl) for hkl in FORBIDDEN}
    return abs(result["lattice_parameter_angstrom"] - 3.735) < 0.018 and abs(result["zero_shift_two_theta_deg"] + 0.27) < 0.018 and table["p111"]["assigned_hkl"] == [1, 1, 1] and table["p311"]["assigned_hkl"] == [3, 1, 1] and all(tuple(row["assigned_hkl"]) not in forbidden for row in result["peaks"] if row["assigned_hkl"] is not None)


def check_group3():
    # Unit conversion alone is insufficient: compare every representation with an
    # independently computed physical baseline so a unit-invariant legacy formula
    # cannot pass merely by applying the same wrong calculation three times.
    lattice, shift = 3.58, 0.23
    fwhms = (0.30, 0.31, 0.34, 0.39)
    reference = run(payload(lattice=lattice, shift=shift, unit="angstrom", fwhms=fwhms))
    converted = [run(payload(lattice=lattice, shift=shift, unit=unit, fwhms=fwhms)) for unit in ("nm", "pm")]
    ref_assignments = [row["assigned_hkl"] for row in reference["peaks"]]
    expected_sizes = [size_nm(fwhm, 0.12, forward(lattice, hkl, shift), shift) for fwhm, hkl in zip(fwhms, ALLOWED[:4])]
    expected_sizes.sort()
    expected_median = (expected_sizes[1] + expected_sizes[2]) / 2.0
    physical_baseline = (
        abs(reference["lattice_parameter_angstrom"] - lattice) < 0.015
        and abs(reference["zero_shift_two_theta_deg"] - shift) < 0.015
        and abs(reference["crystallite_size_nm"] - expected_median) < 0.8
        and all(abs(rows(reference)[name]["corrected_fwhm_deg"] - math.degrees(math.sqrt(math.radians(fwhm) ** 2 - math.radians(0.12) ** 2))) < 1e-6 for name, fwhm in zip(("p111", "p200", "p220", "p311"), fwhms))
    )
    unit_equivalent = all(
        abs(result["lattice_parameter_angstrom"] - reference["lattice_parameter_angstrom"]) < 1e-6
        and abs(result["zero_shift_two_theta_deg"] - reference["zero_shift_two_theta_deg"]) < 1e-6
        and abs(result["crystallite_size_nm"] - reference["crystallite_size_nm"]) < 1e-6
        and [row["assigned_hkl"] for row in result["peaks"]] == ref_assignments
        for result in converted
    )
    return physical_baseline and unit_equivalent


def check_group4():
    extras = [{"id": "secondary", "two_theta_deg": 61.0, "fwhm_deg": 0.22, "intensity": 6.0}, {"id": "too-narrow", "two_theta_deg": round(forward(3.64, [2, 2, 2], -0.11), 5), "fwhm_deg": 0.10, "intensity": 8.0}]
    data = payload(lattice=3.64, shift=-0.11, fwhms=(0.30, 0.32, 0.35, 0.40), extras=extras)
    result = run(data)
    table = rows(result)
    expected_sizes = [size_nm(fwhm, 0.12, table[name]["predicted_two_theta_deg"], -0.11) for name, fwhm in zip(("p111", "p200", "p220", "p311"), (0.30, 0.32, 0.35, 0.40))]
    expected_sizes.sort()
    expected_median = (expected_sizes[1] + expected_sizes[2]) / 2.0
    return abs(result["lattice_parameter_angstrom"] - 3.64) < 0.018 and abs(result["zero_shift_two_theta_deg"] + 0.11) < 0.018 and result["anomalous_peak_ids"] == ["secondary"] and table["secondary"]["anomalous"] and not table["too-narrow"]["anomalous"] and table["too-narrow"]["corrected_fwhm_deg"] is None and table["too-narrow"]["crystallite_size_nm"] is None and abs(result["crystallite_size_nm"] - expected_median) < 0.8 and all(table[name]["crystallite_size_nm"] is not None for name in ("p111", "p200", "p220", "p311"))


for index, check in enumerate((check_group1, check_group2, check_group3, check_group4), 1):
    try:
        print(f"GROUP{index}={1 if check() else 0}")
    except Exception as exc:
        print(f"GROUP{index}=0")
        print(f"GROUP{index}_ERROR={exc}")
