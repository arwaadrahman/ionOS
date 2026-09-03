#!/usr/bin/env bash
# Hygiene and artifact audit over the change set.
#
# This emits SIGNALS, not verdicts. A clean run does not prove the change is
# safe or complete -- it only means these specific mechanical checks found
# nothing. The agent must still read the actual diff.
#
# Exit status:
#   0  audit ran successfully. Advisory signals MAY still be present and must
#      be reviewed by the verify skill. "PASS WITH SIGNALS" never means
#      "nothing to review".
#   1  a real mechanical hygiene failure was found (conflict markers or
#      whitespace errors, or build/runtime/credential-shaped paths in the
#      change set).
#   2  the audit itself could not execute reliably.
#
# Usage: scripts/verify/diff-audit.sh [base-ref]   (default: HEAD)
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || {
  echo "ERROR: not inside a git repository." >&2
  exit 2
}

BASE="${1:-HEAD}"
if ! git rev-parse --verify --quiet "${BASE}^{commit}" >/dev/null; then
  echo "ERROR: base ref '${BASE}' does not resolve to a commit." >&2
  exit 2
fi

advisory=0
failures=0
advise() { echo "  SIGNAL (advisory): $*"; advisory=$((advisory + 1)); }
fail()   { echo "  FAILURE: $*";          failures=$((failures + 1)); }

if ! TRACKED=$(git diff --name-only "$BASE"); then
  echo "ERROR: 'git diff --name-only ${BASE}' failed." >&2
  exit 2
fi
if ! UNTRACKED=$(git ls-files --others --exclude-standard); then
  echo "ERROR: 'git ls-files --others --exclude-standard' failed." >&2
  exit 2
fi
if ! STAGED=$(git diff --cached --name-only); then
  echo "ERROR: 'git diff --cached --name-only' failed." >&2
  exit 2
fi
CHANGED=$(printf '%s\n%s\n' "$TRACKED" "$UNTRACKED" | sed '/^$/d' | sort -u)

echo "== whitespace and conflict markers =="
if git diff --check "$BASE"; then
  echo "  clean"
else
  fail "git diff --check reported issues above"
fi
echo

echo "== untracked files (advisory: inspect each intended new file) =="
if [ -z "$UNTRACKED" ]; then
  echo "  none"
else
  echo "$UNTRACKED" | sed 's/^/  /'
  advise "untracked files present - confirm each one is intended"
fi
echo

echo "== generated, runtime, or credential-shaped paths in the change set =="
SUSPECT=$(printf '%s\n' "$CHANGED" | grep -E \
  '\.(sqlite3?|db|log|pem|key|p12|pfx|crt)$|(^|/)(dist|build|target|node_modules|\.venv|__pycache__|\.pytest_cache|\.ruff_cache|binaries)/' \
  || true)
if [ -z "$SUSPECT" ]; then
  echo "  none"
else
  echo "$SUSPECT" | sed 's/^/  /'
  fail "build output, runtime data, or credential-shaped files in the change set"
fi
echo

echo "== staged paths =="
if [ -z "$STAGED" ]; then
  echo "  none"
else
  echo "$STAGED" | sed 's/^/  /'
fi
echo

echo "advisory signals: ${advisory}    failures: ${failures}"
echo "NOTE: signals are not proof. Read the actual diff before reporting."
if [ "$failures" -ne 0 ]; then
  echo "RESULT: FAIL"
  exit 1
fi
if [ "$advisory" -ne 0 ]; then
  echo "RESULT: PASS WITH SIGNALS (review every signal above)"
  exit 0
fi
echo "RESULT: PASS"
