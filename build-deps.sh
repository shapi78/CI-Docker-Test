#!/usr/bin/env bash
#
# build-deps.sh — resolve Helm chart dependencies for an umbrella chart and
# every subchart found under its charts/ directory.
#
# Charts are processed DEEPEST-FIRST: a parent's `helm dependency build`
# packages the subcharts it finds, so nested subcharts must have their own
# dependencies resolved before their parent is built. The root chart is built
# last (unless --no-root).
#
set -euo pipefail

# ---- defaults ----------------------------------------------------------------
ROOT="."
CMD="build"            # helm dependency <build|update>
INCLUDE_ROOT=1
HELM="${HELM:-helm}"

usage() {
  cat <<'USAGE'
Usage: build-deps.sh [options]

Resolves Helm dependencies for every chart under <root>/charts (and the root
chart itself), processing the deepest subcharts first.

Options:
  -r, --root DIR   Path to the umbrella chart root (default: .)
  -u, --update     Use 'helm dependency update' (re-resolves version ranges
                   against the repos and rewrites Chart.lock) instead of the
                   default 'helm dependency build' (installs exactly what
                   Chart.lock pins; deterministic / CI-safe).
      --no-root    Process only the subcharts under charts/, skip the root.
  -h, --help       Show this help.

Environment:
  HELM             helm binary to use (default: helm)
USAGE
}

# ---- parse args --------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -r|--root)   ROOT="${2:?--root requires a value}"; shift 2 ;;
    -u|--update) CMD="update"; shift ;;
    --no-root)   INCLUDE_ROOT=0; shift ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

# ---- preflight ---------------------------------------------------------------
command -v "$HELM" >/dev/null 2>&1 \
  || { echo "ERROR: '$HELM' not found on PATH." >&2; exit 1; }
[[ -f "$ROOT/Chart.yaml" ]] \
  || { echo "ERROR: no Chart.yaml at '$ROOT' — is that the chart root?" >&2; exit 1; }

# ---- discover chart directories under <root>/charts -------------------------
mapfile -t FOUND < <(
  if [[ -d "$ROOT/charts" ]]; then
    find "$ROOT/charts" -type f -name Chart.yaml -printf '%h\n'
  fi | sort -u
)

# Sort deepest-first by number of path separators, so nested subcharts resolve
# before their parents.
mapfile -t ORDERED < <(
  for d in "${FOUND[@]:-}"; do
    [[ -n "$d" ]] || continue
    printf '%s\t%s\n' "$(tr -cd '/' <<<"$d" | wc -c)" "$d"
  done | sort -rn -k1,1 | cut -f2-
)

# Root chart goes last (parents after their children).
[[ "$INCLUDE_ROOT" -eq 1 ]] && ORDERED+=("$ROOT")

if [[ "${#ORDERED[@]}" -eq 0 ]]; then
  echo "Nothing to do: no Chart.yaml found under '$ROOT/charts'." >&2
  exit 0
fi

# ---- process -----------------------------------------------------------------
declare -a DONE=() FAILED=()
for dir in "${ORDERED[@]}"; do
  echo "── helm dependency $CMD  $dir"
  if "$HELM" dependency "$CMD" "$dir"; then
    DONE+=("$dir")
  else
    echo "   !! failed in $dir" >&2
    FAILED+=("$dir")
  fi
done

# ---- summary -----------------------------------------------------------------
echo
echo "Summary: ${#DONE[@]} ok, ${#FAILED[@]} failed (command: helm dependency $CMD)."
if [[ "${#FAILED[@]}" -gt 0 ]]; then
  printf '  FAILED: %s\n' "${FAILED[@]}" >&2
  [[ "$CMD" == "build" ]] && \
    echo "  Hint: 'build' needs a committed Chart.lock; for a first resolve use -u/--update." >&2
  exit 1
fi
