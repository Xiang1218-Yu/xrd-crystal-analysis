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

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
python3 -m venv "$TMP/venv" || exit $?
"$TMP/venv/bin/python" -m pip install \
  --no-index \
  --find-links "$TEST_DIR/wheels" \
  --require-hashes \
  --no-deps \
  -r "$TEST_DIR/requirements-test.txt" || exit $?

# Test failures produce zero reward; dependency/setup failures remain verifier
# errors so infrastructure problems are not confused with solution failures.
if PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$TMP/venv/bin/python" -m pytest \
  -q -p no:cacheprovider "$TEST_FILE"; then
  printf '1\n' > "$REWARD"
  exit 0
fi

printf '0\n' > "$REWARD"
exit 0
