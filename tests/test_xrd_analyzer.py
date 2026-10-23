"""Behavioral acceptance tests for the FCC XRD analyzer repair."""
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

WAVELENGTH = 1.5406
ALLOWED = [[1, 1, 1], [2, 0, 0], [2, 2, 0], [3, 1, 1], [2, 2, 2], [4, 0, 0]]
FORBIDDEN = [[1, 0, 0], [2, 1, 1], [2, 2, 1]]
PEAK_IDS = ("p111", "p200", "p220", "p311")


def app_root():
    return Path(os.environ.get("XRD_APP_ROOT", "/workspace"))


def analyzer():
    return app_root() / "src" / "xrd_analyzer.py"


def norm(hkl):
    return sum(index * index for index in hkl)


def forward(lattice, hkl, shift):
    ratio = WAVELENGTH * math.sqrt(norm(hkl)) / (2.0 * lattice)
    return math.degrees(2.0 * math.asin(ratio)) + shift


def corrected_fwhm(fwhm_deg, instrument_deg=0.12):
    return math.degrees(math.sqrt(math.radians(fwhm_deg) ** 2 - math.radians(instrument_deg) ** 2))


def expected_size_nm(fwhm_deg, two_theta_deg, shift, shape_factor=0.9):
    beta = math.radians(corrected_fwhm(fwhm_deg))
    theta = math.radians((two_theta_deg - shift) / 2.0)
    return shape_factor * WAVELENGTH / (beta * math.cos(theta)) / 10.0


def payload(lattice=3.61, shift=0.18, unit="angstrom", fwhms=(0.30, 0.31, 0.34, 0.39), extras=()):
    wavelength = {"angstrom": WAVELENGTH, "nm": WAVELENGTH / 10.0, "pm": WAVELENGTH * 100.0}[unit]
    indexed = list(zip(PEAK_IDS, ALLOWED[:4]))
    peaks = [
        {
            "id": name,
            "two_theta_deg": round(forward(lattice, hkl, shift), 5),
            "fwhm_deg": fwhms[index],
            "intensity": 100.0 - 15.0 * index,
        }
        for index, (name, hkl) in enumerate(indexed)
    ]
    peaks.extend(extras)
    return {
        "crystal_system": "cubic",
        "structure": "fcc",
        "wavelength": {"value": wavelength, "unit": unit},
        "candidate_hkls": ALLOWED + FORBIDDEN,
        "lattice_parameter_bounds_angstrom": [3.45, 3.78],
        "zero_shift_bounds_deg": [-0.35, 0.35],
        "peak_position_tolerance_deg": 0.075,
        "instrument_fwhm_deg": 0.12,
        "shape_factor": 0.9,
        "outlier_tolerance": 0.08,
        "peaks": peaks,
    }


def run(data):
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "input.json"
        output = Path(directory) / "output.json"
        source.write_text(json.dumps(data))
        process = subprocess.run(
            [sys.executable, str(analyzer()), "--input", str(source), "--output", str(output)],
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            raise RuntimeError(process.stderr)
        return json.loads(output.read_text())


def rows(result):
    return {row["id"]: row for row in result["peaks"]}


def baseline_result():
    return run(payload(lattice=3.61, shift=0.18))


def size_case_result():
    extras = [
        {"id": "secondary", "two_theta_deg": 61.0, "fwhm_deg": 0.22, "intensity": 6.0},
        {"id": "too-narrow", "two_theta_deg": round(forward(3.64, [2, 2, 2], -0.11), 5), "fwhm_deg": 0.10, "intensity": 8.0},
    ]
    return run(payload(lattice=3.64, shift=-0.11, fwhms=(0.30, 0.32, 0.35, 0.40), extras=extras))


def test_output_contract_and_order():
    """题面原文：“`peaks`：与输入顺序一一对应，保留 `id`、`intensity`、`fwhm_deg`。”"""
    data = payload()
    result = run(data)
    required = {"id", "intensity", "fwhm_deg", "d_spacing_angstrom", "assigned_hkl", "lattice_parameter_angstrom", "residual_angstrom", "predicted_two_theta_deg", "two_theta_residual_deg", "corrected_fwhm_deg", "crystallite_size_nm", "anomalous"}
    assert result["crystal_system"] == data["crystal_system"]
    assert result["structure"] == data["structure"]
    assert [row["id"] for row in result["peaks"]] == [peak["id"] for peak in data["peaks"]]
    assert all(required <= set(row) for row in result["peaks"])


def test_common_lattice_parameter_for_positive_shift():
    """题面原文：“`lattice_parameter_angstrom`：仅由主相非异常峰得到的公共晶格常数。”"""
    result = baseline_result()
    assert result["lattice_parameter_angstrom"] == pytest.approx(3.61, abs=0.015)
    assert result["anomalous_peak_ids"] == []


def test_common_positive_zero_shift_is_recovered():
    """题面原文：“`zero_shift_two_theta_deg`：估计的共同仪器 2θ 零点偏移。”"""
    result = baseline_result()
    assert result["zero_shift_two_theta_deg"] == pytest.approx(0.18, abs=0.015)


def test_fcc_allowed_peaks_receive_expected_indices():
    """题面原文：“只有 `(h, k, l)` 全为奇数或全为偶数时，反射才被允许。”"""
    table = rows(baseline_result())
    observed = [(table[name]["assigned_hkl"], table[name]["anomalous"]) for name in PEAK_IDS]
    expected = [(hkl, False) for hkl in ALLOWED[:4]]
    assert observed == expected


def test_forbidden_fcc_reflections_are_never_assigned():
    """题面原文：“混合奇偶性的候选晶面不可分配给 FCC 主相峰。”"""
    result = run(payload(lattice=3.735, shift=-0.27))
    forbidden = {tuple(hkl) for hkl in FORBIDDEN}
    assert all(tuple(row["assigned_hkl"]) not in forbidden for row in result["peaks"] if row["assigned_hkl"] is not None)
    assert rows(result)["p111"]["assigned_hkl"] == [1, 1, 1]


def test_common_negative_zero_shift_is_recovered():
    """题面原文：“生成数据符合：`observed_2theta = ideal_2theta + δ`。”"""
    result = run(payload(lattice=3.735, shift=-0.27))
    assert result["lattice_parameter_angstrom"] == pytest.approx(3.735, abs=0.018)
    assert result["zero_shift_two_theta_deg"] == pytest.approx(-0.27, abs=0.018)


def test_no_fcc_allowed_candidate_is_rejected():
    """题面原文：“混合奇偶性的候选晶面不可分配给 FCC 主相峰。”"""
    data = payload()
    data["candidate_hkls"] = FORBIDDEN
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "input.json"
        output = root / "output.json"
        sentinel = b'{"status":"previous-valid-result"}\n'
        source.write_text(json.dumps(data), encoding="utf-8")
        output.write_bytes(sentinel)

        process = subprocess.run(
            [sys.executable, str(analyzer()), "--input", str(source), "--output", str(output)],
            capture_output=True,
            text=True,
            check=False,
        )

        assert process.returncode != 0
        assert "no FCC-allowed candidate hkl" in process.stderr
        assert output.read_bytes() == sentinel
        assert {path.name for path in root.iterdir()} == {source.name, output.name}


def test_residual_only_nearby_peak_is_anomalous():
    """题面原文：“若 `abs(observed_2theta - predicted_2theta) > peak_position_tolerance_deg`，则该峰为异常。”"""
    nearby = {
        "id": "nearby-secondary",
        "two_theta_deg": round(forward(3.61, [2, 0, 0], 0.18) + 0.16, 5),
        "fwhm_deg": 0.24,
        "intensity": 5.0,
    }
    result = run(payload(extras=(nearby,)))
    table = rows(result)
    assert table["nearby-secondary"]["lattice_parameter_angstrom"] == pytest.approx(3.61, abs=0.04)
    assert table["nearby-secondary"]["two_theta_residual_deg"] > 0.075
    assert table["nearby-secondary"]["anomalous"] is True
    assert "nearby-secondary" in result["anomalous_peak_ids"]


def test_nm_wavelength_is_physically_equivalent_to_angstrom():
    """题面原文：“同一物理波长分别表示为 Å、nm 或 pm 时，晶格常数、零点偏移、峰索引、异常判定和尺寸应在数值容差内等价。”"""
    angstrom = run(payload(lattice=3.58, shift=0.23, unit="angstrom"))
    nanometre = run(payload(lattice=3.58, shift=0.23, unit="nm"))
    assert nanometre["lattice_parameter_angstrom"] == pytest.approx(angstrom["lattice_parameter_angstrom"], abs=1e-6)
    assert nanometre["zero_shift_two_theta_deg"] == pytest.approx(angstrom["zero_shift_two_theta_deg"], abs=1e-6)
    assert [row["assigned_hkl"] for row in nanometre["peaks"]] == [row["assigned_hkl"] for row in angstrom["peaks"]]


def test_pm_wavelength_is_physically_equivalent_to_angstrom():
    """题面原文：“同一物理波长分别表示为 Å、nm 或 pm 时，晶格常数、零点偏移、峰索引、异常判定和尺寸应在数值容差内等价。”"""
    angstrom = run(payload(lattice=3.58, shift=0.23, unit="angstrom"))
    picometre = run(payload(lattice=3.58, shift=0.23, unit="pm"))
    assert picometre["crystallite_size_nm"] == pytest.approx(angstrom["crystallite_size_nm"], abs=1e-6)
    assert [row["anomalous"] for row in picometre["peaks"]] == [row["anomalous"] for row in angstrom["peaks"]]


def test_unit_case_matches_independent_physical_baseline():
    """题面原文：“计算前必须转为弧度”，且输出尺寸“单位 nm”。"""
    lattice, shift = 3.58, 0.23
    fwhms = (0.30, 0.31, 0.34, 0.39)
    result = run(payload(lattice=lattice, shift=shift, unit="angstrom", fwhms=fwhms))
    expected_sizes = sorted(expected_size_nm(fwhm, forward(lattice, hkl, shift), shift) for fwhm, hkl in zip(fwhms, ALLOWED[:4]))
    assert result["lattice_parameter_angstrom"] == pytest.approx(lattice, abs=0.015)
    assert result["zero_shift_two_theta_deg"] == pytest.approx(shift, abs=0.015)
    assert result["crystallite_size_nm"] == pytest.approx((expected_sizes[1] + expected_sizes[2]) / 2.0, abs=0.8)


def test_gaussian_instrument_broadening_is_subtracted_in_radians():
    """题面原文：“`β_sample = sqrt(β_observed² - β_instrument²)`，计算前必须转为弧度。”"""
    table = rows(size_case_result())
    observed = [table[name]["corrected_fwhm_deg"] for name in PEAK_IDS]
    expected = [corrected_fwhm(fwhm) for fwhm in (0.30, 0.32, 0.35, 0.40)]
    assert observed == pytest.approx(expected, abs=1e-6)


def test_scherrer_size_uses_sample_broadening_and_bragg_angle():
    """题面原文：“`D = K × λ / (β_sample × cos(θ))`，输出时将 Å 转为 nm。”"""
    result = size_case_result()
    table = rows(result)
    expected = expected_size_nm(0.30, table["p111"]["predicted_two_theta_deg"], -0.11)
    assert table["p111"]["crystallite_size_nm"] == pytest.approx(expected, abs=0.8)
    assert table["p111"]["crystallite_size_nm"] > 1.0


def test_equal_or_smaller_instrument_width_returns_json_null():
    """题面原文：“如果 `β_observed <= β_instrument`，该峰的校正展宽与尺寸必须为 `null`。”"""
    equal = {"id": "equal-width", "two_theta_deg": round(forward(3.64, [2, 2, 2], -0.11), 5), "fwhm_deg": 0.12, "intensity": 8.0}
    smaller = {"id": "smaller-width", "two_theta_deg": round(forward(3.64, [4, 0, 0], -0.11), 5), "fwhm_deg": 0.10, "intensity": 7.0}
    table = rows(run(payload(lattice=3.64, shift=-0.11, extras=(equal, smaller))))
    assert table["equal-width"]["corrected_fwhm_deg"] is None
    assert table["equal-width"]["crystallite_size_nm"] is None
    assert table["smaller-width"]["corrected_fwhm_deg"] is None
    assert table["smaller-width"]["crystallite_size_nm"] is None


def test_secondary_peak_is_anomalous_and_retained_in_output():
    """题面原文：“异常峰不能参与顶层晶格常数、零点偏移或尺寸估计，但仍必须出现在结果中。”"""
    result = size_case_result()
    table = rows(result)
    assert result["anomalous_peak_ids"] == ["secondary"]
    assert table["secondary"]["anomalous"] is True
    assert table["secondary"]["id"] == "secondary"


def test_top_level_size_is_median_of_usable_main_phase_peaks():
    """题面原文：“顶层尺寸应为有效主相非异常峰尺寸的稳健汇总。”"""
    result = size_case_result()
    table = rows(result)
    usable = sorted(table[name]["crystallite_size_nm"] for name in PEAK_IDS)
    assert result["crystallite_size_nm"] == pytest.approx((usable[1] + usable[2]) / 2.0, abs=1e-9)
    assert table["too-narrow"]["crystallite_size_nm"] is None


def test_input_order_is_preserved_when_peaks_are_reordered():
    """题面原文：“`peaks`：与输入顺序一一对应。”"""
    data = payload()
    data["peaks"] = list(reversed(data["peaks"]))
    result = run(data)
    assert [row["id"] for row in result["peaks"]] == [peak["id"] for peak in data["peaks"]]
    assert result["lattice_parameter_angstrom"] == pytest.approx(3.61, abs=0.015)


def test_zero_wavelength_rejection_preserves_existing_output_and_leaves_no_temp_file():
    """题面原文：“`value` 为 `0` 时必须拒绝，且不得创建、覆盖或留下半截的目标输出 JSON。”"""
    data = payload()
    data["wavelength"]["value"] = 0

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "invalid-zero-wavelength.json"
        output = root / "result.json"
        sentinel = '{"status":"previous-valid-result"}\n'
        source.write_text(json.dumps(data), encoding="utf-8")
        output.write_text(sentinel, encoding="utf-8")
        before = {path.name: path.read_bytes() for path in root.iterdir()}

        completed = subprocess.run(
            [sys.executable, str(analyzer()), "--input", str(source), "--output", str(output)],
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode != 0
        assert "wavelength must be a finite positive number" in completed.stderr
        assert output.read_text(encoding="utf-8") == sentinel
        assert {path.name: path.read_bytes() for path in root.iterdir()} == before


@pytest.mark.parametrize(
    "invalid_value",
    [-1.0, float("nan"), float("inf"), float("-inf")],
    ids=["negative", "nan", "positive-infinity", "negative-infinity"],
)
def test_nonpositive_or_nonfinite_wavelength_is_rejected_without_side_effects(invalid_value):
    """题面原文：“`value` 必须是有限正数；负数、NaN 或无穷大时必须拒绝，且不得创建、覆盖或留下半截的目标输出 JSON。”"""
    data = payload()
    data["wavelength"]["value"] = invalid_value

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "invalid-wavelength.json"
        output = root / "result.json"
        sentinel = b'{"status":"previous-valid-result"}\n'
        source.write_text(json.dumps(data), encoding="utf-8")
        output.write_bytes(sentinel)
        before = {path.name: path.read_bytes() for path in root.iterdir()}

        completed = subprocess.run(
            [sys.executable, str(analyzer()), "--input", str(source), "--output", str(output)],
            capture_output=True,
            text=True,
            check=False,
        )

        assert completed.returncode != 0
        assert "wavelength must be a finite positive number" in completed.stderr
        assert output.read_bytes() == sentinel
        assert {path.name: path.read_bytes() for path in root.iterdir()} == before
