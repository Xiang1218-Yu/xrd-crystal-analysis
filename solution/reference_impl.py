#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path


def convert_wavelength(value, unit):
    factors = {"angstrom": 1.0, "nm": 10.0, "pm": 0.01}
    if unit not in factors:
        raise ValueError(f"unsupported wavelength unit: {unit}")
    value = float(value)
    if value <= 0:
        raise ValueError("wavelength must be positive")
    return value * factors[unit]


def _norm(hkl):
    return sum(index * index for index in hkl)


def _predicted_two_theta(a, norm, wavelength, shift):
    ratio = wavelength * math.sqrt(norm) / (2.0 * a)
    if not 0.0 < ratio < 1.0:
        return None
    return math.degrees(2.0 * math.asin(ratio)) + shift


def _lattice_from_peak(observed_two_theta, shift, norm, wavelength):
    corrected = observed_two_theta - shift
    theta = math.radians(corrected / 2.0)
    sine = math.sin(theta)
    if sine <= 0.0:
        return None, None
    d_spacing = wavelength / (2.0 * sine)
    return d_spacing * math.sqrt(norm), d_spacing


def _score(peaks, hkls, a, shift, wavelength, tolerance):
    assignments = []
    inlier_residuals = []
    all_residuals = []
    for peak in peaks:
        choices = []
        for hkl in hkls:
            predicted = _predicted_two_theta(a, _norm(hkl), wavelength, shift)
            if predicted is not None:
                choices.append((abs(float(peak["two_theta_deg"]) - predicted), hkl, predicted))
        if not choices:
            assignments.append((None, None, float("inf")))
            all_residuals.append(float("inf"))
            continue
        residual, hkl, predicted = min(choices, key=lambda item: (item[0], item[1]))
        assignments.append((hkl, predicted, residual))
        all_residuals.append(residual)
        if residual <= tolerance:
            inlier_residuals.append(residual)
    # Maximize the number of supported peaks, then minimize their squared error.
    # The final term yields deterministic behavior for equally supported models.
    return (len(inlier_residuals), -sum(value * value for value in inlier_residuals), -sum(all_residuals)), assignments


def _fit_joint_model(peaks, hkls, wavelength, lattice_bounds, shift_bounds, tolerance):
    lower, upper = lattice_bounds
    shift_lower, shift_upper = shift_bounds
    if lower <= 0 or upper < lower or shift_upper < shift_lower:
        raise ValueError("invalid parameter bounds")

    # Enumerate physically derived seeds across the declared zero-shift interval.
    # A fine deterministic grid is followed by local coordinate refinement.
    step = min(0.0025, max(0.0005, tolerance / 25.0))
    count = max(1, int(math.ceil((shift_upper - shift_lower) / step)))
    shifts = [shift_lower + index * (shift_upper - shift_lower) / count for index in range(count + 1)]
    best = None
    for shift in shifts:
        for peak in peaks:
            observed = float(peak["two_theta_deg"])
            for hkl in hkls:
                lattice, _ = _lattice_from_peak(observed, shift, _norm(hkl), wavelength)
                if lattice is None or not lower <= lattice <= upper:
                    continue
                score, assignments = _score(peaks, hkls, lattice, shift, wavelength, tolerance)
                candidate = (score, lattice, shift, assignments)
                if best is None or candidate[0] > best[0]:
                    best = candidate
    if best is None or best[0][0] == 0:
        raise ValueError("no jointly consistent model within the declared bounds")

    _, lattice, shift, _ = best
    # Small coordinate searches reduce gridding error while preserving reproducibility.
    for lattice_step, shift_step in ((0.004, 0.001), (0.0008, 0.0002)):
        improved = True
        while improved:
            improved = False
            for candidate_lattice in (lattice - lattice_step, lattice, lattice + lattice_step):
                for candidate_shift in (shift - shift_step, shift, shift + shift_step):
                    if not (lower <= candidate_lattice <= upper and shift_lower <= candidate_shift <= shift_upper):
                        continue
                    score, assignments = _score(peaks, hkls, candidate_lattice, candidate_shift, wavelength, tolerance)
                    candidate = (score, candidate_lattice, candidate_shift, assignments)
                    if candidate[0] > best[0]:
                        best = candidate
                        lattice, shift = candidate_lattice, candidate_shift
                        improved = True
    return lattice, shift, _score(peaks, hkls, lattice, shift, wavelength, tolerance)[1]


def analyze(payload):
    wavelength = convert_wavelength(payload["wavelength"]["value"], payload["wavelength"]["unit"])
    hkls = [tuple(int(value) for value in hkl) for hkl in payload["candidate_hkls"]]
    if not hkls or any(len(hkl) != 3 or any(value < 0 for value in hkl) or _norm(hkl) == 0 for hkl in hkls):
        raise ValueError("invalid candidate hkl")
    if payload.get("crystal_system") != "cubic":
        raise ValueError("only cubic crystal_system is supported")

    lattice_bounds = tuple(float(value) for value in payload["lattice_parameter_bounds_angstrom"])
    shift_bounds = tuple(float(value) for value in payload.get("zero_shift_bounds_deg", [0.0, 0.0]))
    tolerance = float(payload.get("peak_position_tolerance_deg", payload.get("outlier_tolerance", 0.05)))
    if tolerance < 0:
        raise ValueError("peak_position_tolerance_deg must be non-negative")
    peaks = payload["peaks"]
    if not peaks:
        raise ValueError("at least one peak is required")

    lattice, shift, assignments = _fit_joint_model(peaks, hkls, wavelength, lattice_bounds, shift_bounds, tolerance)
    rows = []
    for peak, (hkl, predicted, position_residual) in zip(peaks, assignments):
        if hkl is None:
            raise ValueError("no valid prediction for peak")
        row_lattice, d_spacing = _lattice_from_peak(float(peak["two_theta_deg"]), shift, _norm(hkl), wavelength)
        anomalous = position_residual > tolerance
        rows.append({
            "id": peak["id"],
            "intensity": peak["intensity"],
            "d_spacing_angstrom": d_spacing,
            "assigned_hkl": list(hkl),
            "lattice_parameter_angstrom": row_lattice,
            "residual_angstrom": abs(row_lattice - lattice),
            "predicted_two_theta_deg": predicted,
            "two_theta_residual_deg": position_residual,
            "anomalous": anomalous,
        })

    # Re-average non-anomalous peak-derived parameters and re-evaluate once.
    # This makes the reported a an observable robust estimate rather than a grid seed.
    inlier_lattices = [row["lattice_parameter_angstrom"] for row in rows if not row["anomalous"]]
    if not inlier_lattices:
        raise ValueError("no inlier peaks")
    lattice = sum(inlier_lattices) / len(inlier_lattices)
    _, assignments = _score(peaks, hkls, lattice, shift, wavelength, tolerance)
    for row, peak, (hkl, predicted, position_residual) in zip(rows, peaks, assignments):
        row_lattice, d_spacing = _lattice_from_peak(float(peak["two_theta_deg"]), shift, _norm(hkl), wavelength)
        row.update({
            "d_spacing_angstrom": d_spacing,
            "assigned_hkl": list(hkl),
            "lattice_parameter_angstrom": row_lattice,
            "residual_angstrom": abs(row_lattice - lattice),
            "predicted_two_theta_deg": predicted,
            "two_theta_residual_deg": position_residual,
            "anomalous": position_residual > tolerance,
        })

    return {
        "crystal_system": payload["crystal_system"],
        "lattice_parameter_angstrom": float(lattice),
        "zero_shift_two_theta_deg": float(shift),
        "peaks": rows,
        "anomalous_peak_ids": [row["id"] for row in rows if row["anomalous"]],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text())
    Path(args.output).write_text(json.dumps(analyze(payload), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
