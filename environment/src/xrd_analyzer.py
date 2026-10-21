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
    lower, upper = payload["lattice_parameter_bounds_angstrom"]

    # Analyze each recorded diffraction peak against the candidate crystal planes.
    provisional = []
    for peak in payload["peaks"]:
        theta = float(peak["two_theta_deg"])
        d_spacing = wavelength / (2.0 * math.sin(theta))
        candidates = []
        for hkl in candidate_hkls:
            norm = sum(v * v for v in hkl)
            candidates.append((d_spacing / math.sqrt(norm), hkl))
        provisional.append((peak, d_spacing, candidates))

    all_values = [a for _, _, candidates in provisional for a, _ in candidates]
    center = sorted(all_values)[len(all_values) // 2]
    rows = []
    for peak, d_spacing, candidates in provisional:
        lattice, hkl = min(candidates, key=lambda item: abs(item[0] - center))
        rows.append({
            "id": peak["id"],
            "intensity": peak["intensity"],
            "d_spacing_angstrom": d_spacing,
            "assigned_hkl": list(hkl),
            "lattice_parameter_angstrom": lattice,
            "residual_angstrom": abs(lattice - center),
            "anomalous": abs(lattice - center) > float(payload["outlier_tolerance"]) or not (lower <= lattice <= upper),
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
