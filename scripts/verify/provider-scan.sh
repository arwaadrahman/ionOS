#!/usr/bin/env bash
# Provider trust-boundary sweep.
#
# This is the manual security check that was pasted into the Phase 2C phase
# prompts and run by hand. It asserts the boundaries that must hold no matter
# what changed:
#
#   * only allowlisted Google methods are reachable from Rust
#   * no wildcard If-Match is ever sent
#   * only the accepted OAuth scopes appear
#   * no token or credential handling leaks into Python or the renderer
#
# Provider methods are discovered GENERICALLY within the security-relevant
# Google Calendar namespaces and then checked against the closed allowed set, so
# a newly added method is caught precisely because it is unknown. A scanner that
# only looked for names it already knew would be blind to exactly the mistake
# this exists to catch.
#
# LIMITATION -- namespaces. The watched namespaces are the prefixes of the
# manifest's allowed methods, unioned with the calendar-management and sharing
# namespaces docs/SECURITY.md forbids (`calendars`, `calendarList`, `acl`). That
# is not proof that an entirely new provider namespace could never be
# introduced: a method under some unrelated namespace would not be matched here.
# Ion has no central registry of permitted Google namespaces, and inventing one
# solely for this script would create a second authority; the manifest plus
# SECURITY.md remain the owners.
#
# contracts/calendar-write-vocabulary.json is the authority for the allowed
# method set. If it is missing, unparseable, or empty, the scan exits 2 rather
# than falling back to a hardcoded set -- a silent fallback after a damaged
# authority file would report PASS against the wrong contract.
#
# Comment and documentation lines are excluded, since the docs legitimately name
# the forbidden forms in order to forbid them. Inline `#[cfg(test)]` modules
# live inside production Rust files, so no .rs file is excluded for containing
# tests; a false-positive test literal is reviewed rather than made invisible.
#
# Exit status:
#   0  every boundary held.
#   1  at least one boundary violation.
#   2  the scan could not run reliably.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || {
  echo "ERROR: not inside a git repository." >&2
  exit 2
}

RUST_DIR="apps/desktop/src-tauri/src"
PY_DIR="apps/api/ion_api"
WEB_DIR="apps/desktop/src"
MANIFEST="contracts/calendar-write-vocabulary.json"

# Real test locations only. A production file whose name merely contains the
# letters "test" or "spec" -- CalendarInspector.tsx, for instance -- must still
# be scanned.
TEST_PATH_RE='(^|/)tests?/|\.(test|spec)\.(ts|tsx|js|jsx)$|(^|/)test_[^/]*\.py$|(^|/)[^/]*_test\.(py|rs)$'

for d in "$RUST_DIR" "$PY_DIR" "$WEB_DIR"; do
  [ -d "$d" ] || { echo "ERROR: expected directory '$d' is missing." >&2; exit 2; }
done

failures=0
fail() { echo "  VIOLATION: $*"; failures=$((failures + 1)); }

# --- production Rust sources, discovered recursively once and reused ---------
RUST_FILES=()
while IFS= read -r f; do
  [ -n "$f" ] && RUST_FILES+=("$f")
done < <(find "$RUST_DIR" -type f -name '*.rs' | sort)
if [ "${#RUST_FILES[@]}" -eq 0 ]; then
  echo "ERROR: no .rs files found under ${RUST_DIR}." >&2
  echo "       Refusing to report a security result against no source." >&2
  exit 2
fi
echo "== production Rust sources scanned (${#RUST_FILES[@]}) =="
printf '  %s\n' "${RUST_FILES[@]}"
echo

# Strip //, ///, and # comment lines so documentation that names a forbidden
# form is not mistaken for code that uses it.
code_only() { grep -vhE '^[[:space:]]*(//|#)' -- "${RUST_FILES[@]}" 2>/dev/null || true; }

# --- allowed method set: from the manifest, or the scan is unreliable --------
if [ ! -f "$MANIFEST" ]; then
  echo "ERROR: ${MANIFEST} is missing." >&2
  echo "       It is the authority for the allowed provider-method set; without" >&2
  echo "       it this scan cannot judge what is allowed. (Branches predating" >&2
  echo "       the manifest cannot be scanned by this script.)" >&2
  exit 2
fi
command -v python3 >/dev/null 2>&1 || {
  echo "ERROR: python3 is required to parse ${MANIFEST}." >&2; exit 2; }
if ! ALLOWED_METHODS=$(python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as error:
    print("parse error: %s" % error, file=sys.stderr); raise SystemExit(1)
methods = d.get("provider", {}).get("methods")
if not isinstance(methods, list) or not methods:
    print("provider.methods missing or empty", file=sys.stderr); raise SystemExit(1)
print(" ".join(methods))' "$MANIFEST"); then
  echo "ERROR: ${MANIFEST} exists but its provider.methods set is unusable." >&2
  echo "       Refusing to fall back to a hardcoded allowed set." >&2
  exit 2
fi

# Watched namespaces: prefixes of the allowed methods, plus the management and
# sharing namespaces SECURITY.md forbids. See the LIMITATION note above.
NAMESPACES="calendars calendarList acl"
for m in $ALLOWED_METHODS; do
  NAMESPACES="${NAMESPACES} ${m%%.*}"
done
NS_ALT=$(printf '%s\n' $NAMESPACES | sort -u | paste -sd'|' -)
NAMESPACE_RE="(${NS_ALT})\.[A-Za-z_][A-Za-z0-9_]*"

# --- provider methods --------------------------------------------------------
echo "== reachable Google methods in Rust =="
echo "  allowed (from manifest): ${ALLOWED_METHODS}"
echo "  watched namespaces:      ${NS_ALT}"
# Restricted to double-quoted string literals. Ion names provider methods as
# strings (the PROVIDER_METHODS inventory); bare `namespace.method` tokens in
# Rust are ordinary method calls on local values -- `calendars.len()` on a Vec
# is not a Google API call. Matching outside string literals produced exactly
# those false positives.
#
# LIMITATION: this detects DECLARED provider method names. It cannot infer a
# method from ad-hoc HTTP verb plus URL-path construction; the wildcard
# If-Match and OAuth-scope checks below cover that surface from other angles.
FOUND=$(code_only \
  | grep -v 'googleapis\.com/auth/' \
  | grep -oE '"[^"]*"' \
  | grep -oE "$NAMESPACE_RE" \
  | sort -u || true)
if [ -z "$FOUND" ]; then
  echo "ERROR: no provider methods discovered across ${#RUST_FILES[@]} Rust files." >&2
  echo "       A non-empty production provider implementation must not be" >&2
  echo "       invisible to this scan; a moved path or broken pattern would" >&2
  echo "       otherwise look like a clean security result." >&2
  echo "       (Allowed methods need not all be exercised -- but zero" >&2
  echo "       discovered means the scan is not seeing the real code.)" >&2
  exit 2
fi
while IFS= read -r m; do
  [ -n "$m" ] || continue
  case " ${ALLOWED_METHODS} " in
    *" ${m} "*) echo "  ok:      ${m}" ;;
    *) fail "Google method '${m}' is reachable but not in the allowed set" ;;
  esac
done <<<"$FOUND"
echo

# --- wildcard If-Match -------------------------------------------------------
echo "== wildcard If-Match =="
WILD=$(code_only | grep -nE 'If-Match' | grep -E '"\*"|\*"' || true)
if [ -z "$WILD" ]; then
  echo "  none - conditional writes use an exact ETag"
else
  echo "$WILD" | sed 's/^/  /'
  fail "a wildcard If-Match appears in non-comment Rust code"
fi
echo

# --- OAuth scopes ------------------------------------------------------------
# Closed set owned by docs/SECURITY.md ("accepted OAuth set"). Update there
# first; this scan enforces, it does not decide.
ALLOWED_SCOPES="https://www.googleapis.com/auth/calendar.calendarlist.readonly
https://www.googleapis.com/auth/calendar.events.readonly
https://www.googleapis.com/auth/calendar.events"

echo "== OAuth scopes (accepted set owned by docs/SECURITY.md) =="
SCOPES=$(grep -hoE 'https://www\.googleapis\.com/auth/[a-zA-Z.]+' "${RUST_FILES[@]}" 2>/dev/null | sort -u || true)
if [ -z "$SCOPES" ]; then
  echo "ERROR: no OAuth scope literals found across ${#RUST_FILES[@]} Rust files." >&2
  echo "       The production Rust OAuth implementation is expected to contain" >&2
  echo "       them, so finding none means this scan is not seeing the real" >&2
  echo "       code. Treating as unreliable rather than PASS." >&2
  exit 2
fi
while IFS= read -r s; do
  [ -n "$s" ] || continue
  if grep -qxF "$s" <<<"$ALLOWED_SCOPES"; then
    echo "  ok:        $s"
  else
    fail "unexpected OAuth scope: $s"
  fi
done <<<"$SCOPES"
echo

# --- credential boundary -----------------------------------------------------
echo "== credentials outside Rust =="
# Handling-shaped, not bare words: a credential being read, assigned, keyed, or
# sent. Prose that merely names one -- the renderer's setup copy saying to put a
# `client_secret` in the OAuth config file -- is not credential handling and
# must not be reported as a boundary violation.
CRED='(access_token|refresh_token|client_secret)'
RAW=$(grep -rniE "\.${CRED}\b|${CRED}[[:space:]]*[:=]|\"${CRED}\"|'${CRED}'|\[[\"']${CRED}[\"']\]|[Bb]earer[[:space:]]+[\$\{\"a-z]" \
  "$PY_DIR" "$WEB_DIR" --include='*.py' --include='*.ts' --include='*.tsx' 2>/dev/null || true)
LEAK=""
if [ -n "$RAW" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    path="${line%%:*}"
    grep -qE "$TEST_PATH_RE" <<<"$path" && continue   # genuine test location
    LEAK+="${line}"$'\n'
  done <<<"$RAW"
fi
LEAK=$(printf '%s' "$LEAK" | sed '/^$/d')
if [ -z "$LEAK" ]; then
  echo "  none - tokens and credentials stay inside Rust"
else
  echo "$LEAK" | sed 's/^/  /'
  fail "token or credential handling appears in Python or the renderer"
fi
echo

echo "violations: ${failures}"
if [ "$failures" -ne 0 ]; then
  echo "RESULT: FAIL"
  exit 1
fi
echo "RESULT: PASS"
echo "NOTE: covers these specific boundaries only. It is not a general security"
echo "      review, and it cannot see behaviour introduced at runtime."
