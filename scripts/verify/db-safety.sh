#!/usr/bin/env bash
# Answer one question: is it currently safe to run an Ion writer or runtime
# entrypoint without touching the owner's production data?
#
# apps/api/ion_api/settings.py:default_data_dir() returns the PRODUCTION
# directory whenever ION_DATA_DIR is unset, so "unset" is not neutral -- it
# means any writer entrypoint would open owner data.
#
# Guarded:  python -m ion_api, npm run dev / dev:api, npm run dev:desktop,
#           tauri dev / tauri build, the packaged ion-api sidecar
#           -- all require an explicit non-production ION_DATA_DIR.
# Exempt:   pytest / npm run test:py, which use isolated temporary directories.
#
# Paths are compared after canonical resolution, so trailing slashes, "..",
# symlinks, and equivalent spellings are handled. The production directory AND
# any descendant of it are UNSAFE; the containment test is boundary-safe, so a
# sibling such as "Ion OS Backup" is not falsely matched. If resolution is
# unreliable the script exits 2 rather than assuming safe.
#
# No database or directory contents are read or enumerated. Only the resolved
# paths and whether the production directory exists are reported.
#
# Exit status:
#   0  ION_DATA_DIR is explicitly set and resolves outside production.
#   1  unset (would default to production), or resolves to production or a
#      path inside it.
#   2  cannot determine reliably.
set -uo pipefail

if [ -z "${HOME:-}" ]; then
  echo "ERROR: HOME is unset; cannot locate the production directory." >&2
  exit 2
fi

PROD="${HOME}/Library/Application Support/Ion OS"
SAFE="${HOME}/Library/Application Support/Ion OS Rebuild"

# Canonicalise a path that may not exist yet. Prefer realpath -m; fall back to
# python3. Print nothing and return nonzero if neither is reliable.
canonicalise() {
  local target="$1" out=""
  if command -v realpath >/dev/null 2>&1; then
    if out=$(realpath -m -- "$target" 2>/dev/null) && [ -n "$out" ]; then
      printf '%s\n' "$out"; return 0
    fi
  fi
  if command -v python3 >/dev/null 2>&1; then
    if out=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$target" 2>/dev/null) \
       && [ -n "$out" ]; then
      printf '%s\n' "$out"; return 0
    fi
  fi
  return 1
}

if ! PROD_RESOLVED=$(canonicalise "$PROD"); then
  echo "ERROR: could not canonically resolve the production path." >&2
  echo "       Neither 'realpath -m' nor python3 was usable." >&2
  exit 2
fi

echo "== paths =="
echo "  production (resolved):   ${PROD_RESOLVED}"
if [ -d "$PROD" ]; then
  echo "  production directory:    exists"
else
  echo "  production directory:    absent"
fi

if [ -z "${ION_DATA_DIR:-}" ]; then
  echo "  ION_DATA_DIR:            (unset)"
  echo
  echo "== verdict =="
  echo "  UNSAFE: ION_DATA_DIR is unset."
  echo "          settings.py defaults to the PRODUCTION directory, so a writer"
  echo "          entrypoint would open the owner's data."
  echo "          Export before runtime work:"
  echo "            export ION_DATA_DIR=\"${SAFE}\""
  echo
  echo "RESULT: NOT SAFE FOR RUNTIME WORK"
  echo "NOTE: expected and harmless if no Ion writer or runtime entrypoint was"
  echo "      run. A hard blocker if one was."
  exit 1
fi

if ! DATA_RESOLVED=$(canonicalise "$ION_DATA_DIR"); then
  echo "  ION_DATA_DIR:            ${ION_DATA_DIR} (unresolvable)"
  echo
  echo "ERROR: could not canonically resolve ION_DATA_DIR; refusing to guess." >&2
  exit 2
fi

echo "  ION_DATA_DIR (resolved): ${DATA_RESOLVED}"
echo
echo "== verdict =="
case "$DATA_RESOLVED" in
  "$PROD_RESOLVED" | "$PROD_RESOLVED"/*)
    echo "  UNSAFE: ION_DATA_DIR resolves to the owner's PRODUCTION directory,"
    echo "          or to a path inside it."
    echo
    echo "RESULT: NOT SAFE FOR RUNTIME WORK"
    exit 1
    ;;
esac
echo "  safe: resolves outside the production directory."
echo
echo "RESULT: SAFE FOR RUNTIME WORK"
echo "NOTE: this confirms only that runtime work is pointed away from owner"
echo "      data. It makes no other claim about the chosen directory."
