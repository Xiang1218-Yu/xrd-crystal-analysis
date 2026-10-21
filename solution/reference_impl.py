#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path


def convert_wavelength(value, unit):
    factors = {"angstrom": 1.0, "nm": 10.0, "pm": 0.01}
    if unit not in factors:
        raise ValueError(f"unsupported wavelength unit: {unit}")
    return float(value) * factors[unit]


def analyze(payload):
    wavelength = convert_wavelength(payload["wavelength"]["value"], payload["wavelength"]["unit"])
    candidate_hkls = [tuple(int(x) for x in hkl) for hkl in payload["candidate_hkls"]]
    if any(len(hkl) != 3 or hkl == (0, 0, 0) for hkl in candidate_hkls):
        raise ValueError("invalid candidate hkl")
    lower, upper = (float(x) for x in payload["lattice_parameter_bounds_angstrom"])
    tolerance = float(payload["outlier_tolerance"])

    provisional = []
    for peak in payload["peaks"]:
        theta_rad = math.radians(float(peak["two_theta_deg"]) / 2.0)
        sine = math.sin(theta_rad)
        if sine <= 0:
            raise ValueError("invalid diffraction angle")
        d_spacing = wavelength / (2.0 * sine)
        candidates = []
        for hkl in candidate_hkls:
            norm = sum(v * v for v in hkl)
            candidates.append((d_spacing * math.sqrt(norm), hkl))
        valid = [(a, hkl) for a, hkl in candidates if lower <= a <= upper]
        provisional.append((peak, d_spacing, candidates, valid))

    valid_values = [a for _, _, _, valid in provisional for a, _ in valid]
    if not valid_values:
        raise ValueError("no candidate lattice parameter in bounds")
    center = sorted(valid_values)[len(valid_values) // 2]
    rows = []
    for peak, d_spacing, candidates, valid in provisional:
        pool = valid if valid else candidates
        lattice, hkl = min(pool, key=lambda item: abs(item[0] - center))
        residual = abs(lattice - center)
        rows.append({
            "id": peak["id"],
            "intensity": peak["intensity"],
            "d_spacing_angstrom": d_spacing,
            "assigned_hkl": list(hkl),
            "lattice_parameter_angstrom": lattice,
            "residual_angstrom": residual,
            "anomalous": not valid or residual > tolerance,
        })

    inliers = [row["lattice_parameter_angstrom"] for row in rows if not row["anomalous"]]
    estimate = sum(inliers) / len(inliers) if inliers else center
    return {
        "crystal_system": payload["crystal_system"],
        "lattice_parameter_angstrom": estimate,
        "peaks": rows,
        "anomalous_peak_ids": [row["id"] for row in rows if row["anomalous"]],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text())
    result = analyze(payload)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
