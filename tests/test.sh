#!/usr/bin/env bash
set -u

REWARD=${REWARD_FILE:-/logs/verifier/reward.txt}
mkdir -p "$(dirname "$REWARD")"
printf '0\n' > "$REWARD"

TEST_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f /workspace/src/xrd_analyzer.py ]; then
  export XRD_APP_ROOT=/workspace
  TEST_FILE="$TEST_DIR/test_xrd_analyzer.py"
else
  ROOT="$(cd "$TEST_DIR/.." && pwd)"
  export XRD_APP_ROOT="$ROOT/environment"
  TEST_FILE="$ROOT/tests/test_xrd_analyzer.py"
fi

# The image exposes exact-version, SHA-256-verified verifier wheels through
# PYTHONPATH. Confirm the expected distributions before collecting any tests.
python3 - <<'PY' || exit $?
from importlib.metadata import version

expected = {
    "iniconfig": "2.3.1",
    "packaging": "26.3",
    "pluggy": "1.7.0",
    "Pygments": "2.21.0",
    "pytest": "9.1.1",
}
for distribution, required in expected.items():
    actual = version(distribution)
    if actual != required:
        raise SystemExit(f"{distribution}: expected {required}, found {actual}")
PY

# Test failures produce zero reward; setup failures remain verifier errors so
# infrastructure problems are not confused with solution failures.
if PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest \
  -q -p no:cacheprovider "$TEST_FILE"; then
  printf '1\n' > "$REWARD"
  exit 0
fi

printf '0\n' > "$REWARD"
exit 0
