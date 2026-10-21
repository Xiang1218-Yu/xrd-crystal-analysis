#!/usr/bin/env python3
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1])
script = root / "src" / "xrd_analyzer.py"

def run(payload):
    with tempfile.TemporaryDirectory() as td:
        inp = Path(td) / "in.json"
        out = Path(td) / "out.json"
        inp.write_text(json.dumps(payload))
        p = subprocess.run([sys.executable, str(script), "--input", str(inp), "--output", str(out)], capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(p.stderr)
        return json.loads(out.read_text())

def base(unit="angstrom", wavelength=1.5406):
    return {
        "crystal_system": "cubic",
        "wavelength": {"value": wavelength, "unit": unit},
        "candidate_hkls": [[1,1,1], [2,0,0], [2,2,0], [3,1,1], [2,2,2]],
        "lattice_parameter_bounds_angstrom": [3.4, 3.8],
        "outlier_tolerance": 0.08,
        "peaks": [
            {"id": "p111", "two_theta_deg": 43.297, "intensity": 100.0},
            {"id": "p200", "two_theta_deg": 50.433, "intensity": 70.0},
            {"id": "p220", "two_theta_deg": 74.130, "intensity": 45.0},
            {"id": "p311", "two_theta_deg": 89.940, "intensity": 22.0},
        ],
    }

def check_group1():
    out = run(base())
    expected = {"p111": (1.0, [1,1,1]), "p200": (1.0, [2,0,0]), "p220": (1.0, [2,2,0]), "p311": (1.0, [3,1,1])}
    for row in out["peaks"]:
        a, hkl = expected[row["id"]]
        if row["assigned_hkl"] != hkl or abs(row["lattice_parameter_angstrom"] - 3.61) > 0.03:
            return False
        if abs(row["d_spacing_angstrom"] - 3.61 / math.sqrt(sum(x*x for x in hkl))) > 0.02:
            return False
    return abs(out["lattice_parameter_angstrom"] - 3.61) <= 0.03

def check_group2():
    ref = base("angstrom", 1.5406)
    nm = base("nm", 0.15406)
    pm = base("pm", 154.06)
    a = run(ref)["lattice_parameter_angstrom"]
    b = run(nm)["lattice_parameter_angstrom"]
    c = run(pm)["lattice_parameter_angstrom"]
    return abs(a-b) < 1e-6 and abs(a-c) < 1e-6 and abs(a-3.61) < 0.03

def check_group3():
    out = run(base())
    return all(not row["anomalous"] for row in out["peaks"]) and out["anomalous_peak_ids"] == []

def check_group4():
    payload = base()
    payload["peaks"].append({"id": "bad", "two_theta_deg": 61.0, "intensity": 6.0})
    out = run(payload)
    bad = next(row for row in out["peaks"] if row["id"] == "bad")
    return bad["anomalous"] and out["anomalous_peak_ids"] == ["bad"] and abs(out["lattice_parameter_angstrom"] - 3.61) < 0.03

checks = [check_group1, check_group2, check_group3, check_group4]
for i, check in enumerate(checks, 1):
    try:
        value = 1 if check() else 0
    except Exception as exc:
        print(f"GROUP{i}=0")
        print(f"GROUP{i}_ERROR={exc}")
        continue
    print(f"GROUP{i}={value}")
