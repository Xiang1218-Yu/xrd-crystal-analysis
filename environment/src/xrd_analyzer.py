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
    """Legacy implementation with intentionally incomplete physical handling."""
    wavelength = convert_wavelength(payload["wavelength"]["value"], payload["wavelength"]["unit"])
    hkls = [tuple(int(value) for value in hkl) for hkl in payload["candidate_hkls"]]
    rows = []
    estimates = []
    for peak in payload["peaks"]:
        # Incorrectly treats measured 2theta degrees as the radian theta angle,
        # ignores the shared instrumental shift, and permits forbidden FCC planes.
        d_spacing = wavelength / (2.0 * math.sin(float(peak["two_theta_deg"])))
        hkl = min(hkls, key=lambda plane: sum(value * value for value in plane))
        lattice = d_spacing / math.sqrt(sum(value * value for value in hkl))
        estimates.append(lattice)
        rows.append({
            "id": peak["id"], "intensity": peak["intensity"], "fwhm_deg": peak.get("fwhm_deg"),
            "d_spacing_angstrom": d_spacing, "assigned_hkl": list(hkl),
            "lattice_parameter_angstrom": lattice, "residual_angstrom": 0.0,
            "predicted_two_theta_deg": float(peak["two_theta_deg"]), "two_theta_residual_deg": 0.0,
            "corrected_fwhm_deg": peak.get("fwhm_deg"),
            "crystallite_size_nm": wavelength / max(float(peak.get("fwhm_deg", 1.0)), 1e-12) / 10.0,
            "anomalous": False,
        })
    center = sum(estimates) / len(estimates)
    return {
        "crystal_system": payload["crystal_system"],
        "structure": payload.get("structure"),
        "lattice_parameter_angstrom": center,
        "zero_shift_two_theta_deg": 0.0,
        "crystallite_size_nm": sum(row["crystallite_size_nm"] for row in rows) / len(rows),
        "peaks": rows,
        "anomalous_peak_ids": [],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = analyze(json.loads(Path(args.input).read_text()))
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
