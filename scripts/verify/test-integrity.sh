#!/usr/bin/env bash
# Look for signs that tests were weakened to make a change pass.
#
# EVERY FINDING HERE IS A SIGNAL, NOT A VERDICT.
#
# These are counting heuristics. They cannot tell a legitimate consolidation
# from a gutted assertion, and a silent run does NOT mean tests were
# semantically preserved -- an assertion can be loosened without changing any
# count at all. The verify skill must read the actual test diff and judge.
# Nothing in this script may be quoted as proof that tests are intact.
#
# Exit status:
#   0  the scan ran. Signals may be present and all of them require review.
#   2  the scan could not run reliably.
#
# Usage: scripts/verify/test-integrity.sh [base-ref]   (default: HEAD)
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

# Deliberately narrow: a directory named tests/, or a file named with a
# recognised test suffix/prefix. Ordinary source files must not match.
TEST_PATH_RE='(^|/)tests?/|\.(test|spec)\.(ts|tsx|js|jsx)$|(^|/)test_[^/]*\.py$|(^|/)[^/]*_test\.(py|rs)$'

if ! CHANGED_TRACKED=$(git diff --name-only --diff-filter=ACMR "$BASE"); then
  echo "ERROR: 'git diff --name-only ${BASE}' failed." >&2
  exit 2
fi
if ! DELETED=$(git diff --name-only --diff-filter=D "$BASE"); then
  echo "ERROR: could not list deleted paths." >&2
  exit 2
fi
if ! UNTRACKED=$(git ls-files --others --exclude-standard); then
  echo "ERROR: 'git ls-files --others' failed." >&2
  exit 2
fi

TEST_FILES=$(printf '%s\n%s\n' "$CHANGED_TRACKED" "$UNTRACKED" \
  | sed '/^$/d' | grep -E "$TEST_PATH_RE" | sort -u || true)
DELETED_TESTS=$(printf '%s\n' "$DELETED" | sed '/^$/d' \
  | grep -E "$TEST_PATH_RE" | sort -u || true)

signals=0
signal() { echo "  SIGNAL: $*"; signals=$((signals + 1)); }

# grep -c prints 0 and exits 1 when nothing matches, so its status is tolerated
# and the output is normalised. Always returns exactly one integer.
count_matches() {
  local pattern="$1" content="$2" n=""
  n=$(grep -cE "$pattern" <<<"$content" 2>/dev/null) || true
  [[ "$n" =~ ^[0-9]+$ ]] || n=0
  printf '%s' "$n"
}

TESTS_RE='^[[:space:]]*(async[[:space:]]+)?def[[:space:]]+test_|(^|[^.[:alnum:]])(test|it)[[:space:]]*\(|#\[(tokio::)?test\]'
ASSERT_RE='(^|[^.[:alnum:]])assert|expect[[:space:]]*\(|assert_eq!|assert_ne!|assert!'
SKIP_RE='pytest\.mark\.(skip|xfail)|pytest\.skip\(|\.(skip|only|todo)[[:space:]]*\(|#\[ignore'

echo "== deleted test files =="
if [ -z "$DELETED_TESTS" ]; then
  echo "  none"
else
  echo "$DELETED_TESTS" | sed 's/^/  /'
  signal "test files were deleted - confirm each removal is intended"
fi
echo

echo "== changed test files =="
if [ -z "$TEST_FILES" ]; then
  echo "  none"
else
  while IFS= read -r file; do
    [ -n "$file" ] || continue
    [ -f "$file" ] || continue
    new=$(cat -- "$file")
    old=$(git show "${BASE}:${file}" 2>/dev/null || printf '')

    nt=$(count_matches "$TESTS_RE"  "$new"); ot=$(count_matches "$TESTS_RE"  "$old")
    na=$(count_matches "$ASSERT_RE" "$new"); oa=$(count_matches "$ASSERT_RE" "$old")
    ns=$(count_matches "$SKIP_RE"   "$new"); os=$(count_matches "$SKIP_RE"   "$old")

    if [ -z "$old" ]; then
      printf '  %s\n    new file: %s tests, %s assertions, %s skip markers\n' \
        "$file" "$nt" "$na" "$ns"
      [ "$ns" -gt 0 ] && signal "${file}: new file already contains ${ns} skip/only/ignore marker(s)"
      continue
    fi

    printf '  %s\n    tests %s -> %s    assertions %s -> %s    skips %s -> %s\n' \
      "$file" "$ot" "$nt" "$oa" "$na" "$os" "$ns"
    [ "$nt" -lt "$ot" ] && signal "${file}: test count fell ${ot} -> ${nt}"
    [ "$na" -lt "$oa" ] && signal "${file}: assertion count fell ${oa} -> ${na}"
    [ "$ns" -gt "$os" ] && signal "${file}: skip/only/xfail/ignore markers rose ${os} -> ${ns}"
  done <<<"$TEST_FILES"
fi
echo

echo "signals: ${signals}"
if [ "$signals" -eq 0 ]; then
  echo "RESULT: NO SIGNALS"
  echo "This does NOT mean tests were preserved. Assertions can be loosened"
  echo "without moving any count. Read the test diff."
else
  echo "RESULT: REVIEW REQUIRED (${signals} signal(s))"
  echo "Read the actual test diff for each file above and decide whether the"
  echo "change weakened what the tests prove."
fi
