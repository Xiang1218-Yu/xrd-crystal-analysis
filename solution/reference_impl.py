#!/usr/bin/env python3
import argparse
import json
import math
import os
import tempfile
from pathlib import Path


UNITS = {"angstrom": 1.0, "nm": 10.0, "pm": 0.01}


def convert_wavelength(value, unit):
    if unit not in UNITS:
        raise ValueError(f"unsupported wavelength unit: {unit}")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("wavelength must be a finite positive number")
    return value * UNITS[unit]


def _norm(hkl):
    return sum(index * index for index in hkl)


def _is_fcc_allowed(hkl):
    parity = [index % 2 for index in hkl]
    return parity[0] == parity[1] == parity[2]


def _forward_two_theta(lattice, hkl, wavelength, shift):
    ratio = wavelength * math.sqrt(_norm(hkl)) / (2.0 * lattice)
    if not 0.0 < ratio < 1.0:
        return None
    return math.degrees(2.0 * math.asin(ratio)) + shift


def _peak_lattice(observed_two_theta, shift, hkl, wavelength):
    theta = math.radians((float(observed_two_theta) - shift) / 2.0)
    sine = math.sin(theta)
    if sine <= 0.0:
        return None, None
    d_spacing = wavelength / (2.0 * sine)
    return d_spacing * math.sqrt(_norm(hkl)), d_spacing


def _score(peaks, allowed_hkls, lattice, shift, wavelength, tolerance):
    assignments = []
    inlier_errors = []
    all_errors = []
    for peak in peaks:
        candidates = []
        for hkl in allowed_hkls:
            predicted = _forward_two_theta(lattice, hkl, wavelength, shift)
            if predicted is not None:
                candidates.append((abs(float(peak["two_theta_deg"]) - predicted), hkl, predicted))
        if not candidates:
            assignments.append((None, None, float("inf")))
            all_errors.append(float("inf"))
            continue
        residual, hkl, predicted = min(candidates, key=lambda item: (item[0], item[1]))
        assignments.append((hkl, predicted, residual))
        all_errors.append(residual)
        if residual <= tolerance:
            inlier_errors.append(residual)
    return (len(inlier_errors), -sum(error * error for error in inlier_errors), -sum(all_errors)), assignments


def _fit_joint_model(peaks, allowed_hkls, wavelength, lattice_bounds, shift_bounds, tolerance):
    lower, upper = lattice_bounds
    shift_lower, shift_upper = shift_bounds
    if lower <= 0 or upper < lower or shift_upper < shift_lower:
        raise ValueError("invalid parameter bounds")
    step = min(0.0025, max(0.0005, tolerance / 25.0))
    count = max(1, int(math.ceil((shift_upper - shift_lower) / step)))
    seeds = []
    for index in range(count + 1):
        shift = shift_lower + index * (shift_upper - shift_lower) / count
        for peak in peaks:
            for hkl in allowed_hkls:
                lattice, _ = _peak_lattice(peak["two_theta_deg"], shift, hkl, wavelength)
                if lattice is not None and lower <= lattice <= upper:
                    score, assignments = _score(peaks, allowed_hkls, lattice, shift, wavelength, tolerance)
                    seeds.append((score, lattice, shift, assignments))
    if not seeds:
        raise ValueError("no jointly consistent FCC model within bounds")
    best = max(seeds, key=lambda item: item[0])
    lattice, shift = best[1], best[2]
    for lattice_step, shift_step in ((0.004, 0.001), (0.0008, 0.0002)):
        improved = True
        while improved:
            improved = False
            for candidate_lattice in (lattice - lattice_step, lattice, lattice + lattice_step):
                for candidate_shift in (shift - shift_step, shift, shift + shift_step):
                    if not (lower <= candidate_lattice <= upper and shift_lower <= candidate_shift <= shift_upper):
                        continue
                    candidate_score, assignments = _score(peaks, allowed_hkls, candidate_lattice, candidate_shift, wavelength, tolerance)
                    candidate = (candidate_score, candidate_lattice, candidate_shift, assignments)
                    if candidate[0] > best[0]:
                        best = candidate
                        lattice, shift = candidate_lattice, candidate_shift
                        improved = True
    return lattice, shift, _score(peaks, allowed_hkls, lattice, shift, wavelength, tolerance)[1]


def _size_for_peak(peak, shift, wavelength, shape_factor):
    observed = math.radians(float(peak["fwhm_deg"]))
    instrument = math.radians(float(peak["instrument_fwhm_deg"]))
    if observed <= instrument:
        return None, None
    beta = math.sqrt(observed * observed - instrument * instrument)
    theta = math.radians((float(peak["two_theta_deg"]) - shift) / 2.0)
    cosine = math.cos(theta)
    if beta <= 0.0 or cosine <= 0.0:
        return None, None
    size_nm = shape_factor * wavelength / (beta * cosine) / 10.0
    return math.degrees(beta), size_nm


def analyze(payload):
    wavelength = convert_wavelength(payload["wavelength"]["value"], payload["wavelength"]["unit"])
    if payload.get("crystal_system") != "cubic" or payload.get("structure") != "fcc":
        raise ValueError("only cubic fcc inputs are supported")
    all_hkls = [tuple(int(value) for value in hkl) for hkl in payload["candidate_hkls"]]
    if not all_hkls or any(len(hkl) != 3 or any(value < 0 for value in hkl) or _norm(hkl) == 0 for hkl in all_hkls):
        raise ValueError("invalid candidate hkl")
    allowed_hkls = [hkl for hkl in all_hkls if _is_fcc_allowed(hkl)]
    if not allowed_hkls:
        raise ValueError("no FCC-allowed candidate hkl")
    peaks = payload["peaks"]
    if not peaks:
        raise ValueError("at least one peak is required")
    lattice_bounds = tuple(float(value) for value in payload["lattice_parameter_bounds_angstrom"])
    shift_bounds = tuple(float(value) for value in payload.get("zero_shift_bounds_deg", [0.0, 0.0]))
    tolerance = float(payload.get("peak_position_tolerance_deg", payload.get("outlier_tolerance", 0.05)))
    if tolerance < 0.0:
        raise ValueError("invalid peak position tolerance")
    shape_factor = float(payload.get("shape_factor", 0.9))

    lattice, shift, assignments = _fit_joint_model(peaks, allowed_hkls, wavelength, lattice_bounds, shift_bounds, tolerance)
    rows = []
    for peak, (hkl, predicted, peak_residual) in zip(peaks, assignments):
        if hkl is None:
            rows.append({"id": peak["id"], "intensity": peak["intensity"], "fwhm_deg": peak.get("fwhm_deg"), "d_spacing_angstrom": None, "assigned_hkl": None, "lattice_parameter_angstrom": None, "residual_angstrom": None, "predicted_two_theta_deg": None, "two_theta_residual_deg": None, "corrected_fwhm_deg": None, "crystallite_size_nm": None, "anomalous": True})
            continue
        row_lattice, d_spacing = _peak_lattice(peak["two_theta_deg"], shift, hkl, wavelength)
        anomalous = peak_residual > tolerance or not (lattice_bounds[0] <= row_lattice <= lattice_bounds[1])
        rows.append({"id": peak["id"], "intensity": peak["intensity"], "fwhm_deg": peak.get("fwhm_deg"), "d_spacing_angstrom": d_spacing, "assigned_hkl": list(hkl), "lattice_parameter_angstrom": row_lattice, "residual_angstrom": abs(row_lattice - lattice), "predicted_two_theta_deg": predicted, "two_theta_residual_deg": peak_residual, "corrected_fwhm_deg": None, "crystallite_size_nm": None, "anomalous": anomalous})

    inlier_lattices = [row["lattice_parameter_angstrom"] for row in rows if not row["anomalous"]]
    if not inlier_lattices:
        raise ValueError("no FCC inlier peaks")
    lattice = sum(inlier_lattices) / len(inlier_lattices)
    _, assignments = _score(peaks, allowed_hkls, lattice, shift, wavelength, tolerance)
    usable_sizes = []
    for row, peak, (hkl, predicted, peak_residual) in zip(rows, peaks, assignments):
        if hkl is None:
            continue
        row_lattice, d_spacing = _peak_lattice(peak["two_theta_deg"], shift, hkl, wavelength)
        anomalous = peak_residual > tolerance or not (lattice_bounds[0] <= row_lattice <= lattice_bounds[1])
        row.update({"d_spacing_angstrom": d_spacing, "assigned_hkl": list(hkl), "lattice_parameter_angstrom": row_lattice, "residual_angstrom": abs(row_lattice - lattice), "predicted_two_theta_deg": predicted, "two_theta_residual_deg": peak_residual, "anomalous": anomalous})
        if not anomalous:
            local_peak = dict(peak)
            local_peak["instrument_fwhm_deg"] = payload["instrument_fwhm_deg"]
            corrected, size = _size_for_peak(local_peak, shift, wavelength, shape_factor)
            row["corrected_fwhm_deg"] = corrected
            row["crystallite_size_nm"] = size
            if size is not None:
                usable_sizes.append(size)
    usable_sizes.sort()
    midpoint = len(usable_sizes) // 2
    size_estimate = None if not usable_sizes else (usable_sizes[midpoint] if len(usable_sizes) % 2 else (usable_sizes[midpoint - 1] + usable_sizes[midpoint]) / 2.0)
    return {"crystal_system": payload["crystal_system"], "structure": payload["structure"], "lattice_parameter_angstrom": float(lattice), "zero_shift_two_theta_deg": float(shift), "crystallite_size_nm": size_estimate, "peaks": rows, "anomalous_peak_ids": [row["id"] for row in rows if row["anomalous"]]}


def write_json_atomically(output_path, result):
    target = Path(output_path)
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = analyze(json.loads(Path(args.input).read_text(encoding="utf-8")))
    write_json_atomically(args.output, result)


if __name__ == "__main__":
    main()
