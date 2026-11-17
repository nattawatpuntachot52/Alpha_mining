#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/sync_codex_skills.sh [OPTIONS]

Sync all skills containing SKILL.md from Alpha_mining/skills/ into
${CODEX_HOME:-$HOME/.codex}/skills/.

Options:
  --symlink            Create symlinks instead of copying (auto-tracks git pull)
  --force              Replace existing skill entries with the same names
  --dry-run            Show actions without modifying files
  --codex-home <path>  Override target CODEX_HOME (default: $CODEX_HOME or ~/.codex)
  -h, --help           Show this help message
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_SKILLS_DIR="$REPO_ROOT/skills"

MODE="copy"
FORCE=0
DRY_RUN=0
TARGET_CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --symlink)
      MODE="symlink"
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --codex-home)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        printf 'Error: --codex-home requires a non-empty path\n' >&2
        exit 2
      fi
      TARGET_CODEX_HOME="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Error: unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ ! -d "$SRC_SKILLS_DIR" ]; then
  printf 'Error: skills directory not found: %s\n' "$SRC_SKILLS_DIR" >&2
  exit 1
fi

SKILLS=()
for candidate in "$SRC_SKILLS_DIR"/*; do
  if [ -d "$candidate" ] && [ -f "$candidate/SKILL.md" ]; then
    SKILLS+=("$(basename "$candidate")")
  fi
done

if [ "${#SKILLS[@]}" -eq 0 ]; then
  printf 'Error: no skills containing SKILL.md found in %s\n' "$SRC_SKILLS_DIR" >&2
  exit 1
fi

DEST_SKILLS_DIR="$TARGET_CODEX_HOME/skills"

# Pre-flight conflict check so we never leave a partially updated state.
CONFLICTS=()
for skill in "${SKILLS[@]}"; do
  dest="$DEST_SKILLS_DIR/$skill"
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    CONFLICTS+=("$dest")
  fi
done

if [ "$FORCE" -eq 0 ] && [ "${#CONFLICTS[@]}" -gt 0 ]; then
  printf 'Refusing to overwrite existing skill path(s) without --force:\n' >&2
  for conflict in "${CONFLICTS[@]}"; do
    printf '  - %s\n' "$conflict" >&2
  done
  printf 'Re-run with --force (or --dry-run to preview) after reviewing backups.\n' >&2
  exit 1
fi

if [ "$DRY_RUN" -eq 0 ]; then
  mkdir -p "$DEST_SKILLS_DIR"
fi

for skill in "${SKILLS[@]}"; do
  src="$SRC_SKILLS_DIR/$skill"
  dest="$DEST_SKILLS_DIR/$skill"

  if [ "$DRY_RUN" -eq 1 ]; then
    if [ -e "$dest" ] || [ -L "$dest" ]; then
      printf '[dry-run] replace %s (%s -> %s)\n' "$dest" "$MODE" "$src"
    else
      printf '[dry-run] %s %s -> %s\n' "$MODE" "$src" "$dest"
    fi
    continue
  fi

  if [ -e "$dest" ] || [ -L "$dest" ]; then
    if [ -L "$dest" ]; then
      rm "$dest"
    else
      rm -rf "$dest"
    fi
  fi

  if [ "$MODE" = "symlink" ]; then
    ln -s "$src" "$dest"
    printf 'linked: %s -> %s\n' "$dest" "$src"
  else
    cp -R "$src" "$dest"
    printf 'copied: %s -> %s\n' "$src" "$dest"
  fi
done
