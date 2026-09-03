#!/usr/bin/env bash
# Run the checks appropriate to what actually changed, then the full repository
# gate. Every command is echoed shell-quoted so the evidence report can quote
# exact invocations rather than paraphrasing them.
#
# All applicable checks run even after one fails: complete evidence is worth
# more than stopping early. The script exits nonzero if ANY check failed, so a
# caller can never mistake partial success for a pass.
#
# Changed-path discovery is fail-loud. A base ref that does not resolve must
# never degrade into a partial path set, because that would silently skip the
# focused checks and still print PASS.
#
# Usage: scripts/verify/run-checks.sh [base-ref]   (default: HEAD)
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || {
  echo "ERROR: not inside a git repository." >&2
  exit 2
}

BASE="${1:-HEAD}"

if ! git rev-parse --verify --quiet "${BASE}^{commit}" >/dev/null; then
  echo "ERROR: base ref '${BASE}' does not resolve to a commit." >&2
  echo "       Refusing to run: changed-path discovery would be incomplete." >&2
  exit 2
fi

if ! TRACKED=$(git diff --name-only "$BASE"); then
  echo "ERROR: 'git diff --name-only ${BASE}' failed." >&2
  exit 2
fi
if ! UNTRACKED=$(git ls-files --others --exclude-standard); then
  echo "ERROR: 'git ls-files --others --exclude-standard' failed." >&2
  exit 2
fi
CHANGED=$(printf '%s\n%s\n' "$TRACKED" "$UNTRACKED" | sed '/^$/d' | sort -u)

FAILED=()
PASSED=()

run() {
  local label="$1"; shift
  printf '$ '; printf '%q ' "$@"; printf '\n'
  "$@"
  local status=$?          # captured before anything else can overwrite it
  echo "   -> exit ${status}"
  echo
  if [ "$status" -eq 0 ]; then
    PASSED+=("$label")
  else
    FAILED+=("${label} (exit ${status})")
  fi
}

echo "== changed paths vs ${BASE} =="
if [ -z "$CHANGED" ]; then
  echo "  (none)"
else
  echo "$CHANGED" | sed 's/^/  /'
fi
echo

echo "== focused checks =="
if grep -q '^apps/api/' <<<"$CHANGED"; then
  run "python tests" uv --directory apps/api run pytest -q
fi
if grep -qE '^apps/desktop/src/' <<<"$CHANGED"; then
  run "typescript tests" npm --workspace @ion/desktop run test
fi
if grep -qE '^apps/desktop/src-tauri/' <<<"$CHANGED"; then
  run "rust tests" cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml
fi
if [ "${#PASSED[@]}" -eq 0 ] && [ "${#FAILED[@]}" -eq 0 ]; then
  echo "  (no focused check matched the changed paths)"
  echo
fi

echo "== repository gate =="
run "npm run validate" npm run validate

echo "== summary =="
# Guarded: under `set -u`, expanding an empty array with "${arr[@]}" is an error
# on the bash 3.2 that ships with macOS. Without this, a run in which every
# check failed would crash here instead of reporting FAIL.
if [ "${#PASSED[@]}" -gt 0 ]; then
  for item in "${PASSED[@]}"; do echo "  PASS  ${item}"; done
fi
if [ "${#FAILED[@]}" -gt 0 ]; then
  for item in "${FAILED[@]}"; do echo "  FAIL  ${item}"; done
fi
echo
if [ "${#FAILED[@]}" -ne 0 ]; then
  echo "RESULT: FAIL (${#FAILED[@]} of $(( ${#PASSED[@]} + ${#FAILED[@]} )) checks failed)"
  exit 1
fi
echo "RESULT: PASS (${#PASSED[@]} checks)"
