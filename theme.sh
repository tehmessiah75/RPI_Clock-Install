#!/usr/bin/env bash
# =============================================================================
#  theme.sh  —  Change the rpi_clock colour theme
#
#  Changes only the theme — does not touch API key, location, or any
#  other settings.
#
#  Usage:
#    bash theme.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; YEL='\033[1;33m'; GRN='\033[0;32m'; CYN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GRN}[ OK ]${NC}  $*"; }
warn() { echo -e "${YEL}[WARN]${NC}  $*"; }
die()  { echo -e "${RED}[FAIL]${NC}  $*" >&2; exit 1; }

# ── Find config file ──────────────────────────────────────────────────────────
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
  TARGET_USER="$SUDO_USER"
else
  TARGET_USER="$USER"
fi
TARGET_HOME=$(eval echo "~$TARGET_USER")
CFG_FILE="$TARGET_HOME/rpi_clock/rpi_clock.cfg"

[ -f "$CFG_FILE" ] || die "Config file not found: $CFG_FILE"

# ── Show current theme ────────────────────────────────────────────────────────
CURRENT_THEME=$(grep -E "^theme\s*=" "$CFG_FILE" | awk -F'=' '{print $2}' \
                | tr -d ' ' || echo "dark_blue")

echo ""
echo -e "${CYN}=============================================================${NC}"
echo -e "${CYN}  rpi_clock  —  Change Theme${NC}"
echo -e "${CYN}=============================================================${NC}"
echo ""
echo -e "  Current theme: ${YEL}${CURRENT_THEME}${NC}"
echo ""
echo "  Select a new colour theme:"
echo "    1) Dark Blue  — dark navy background, white/blue text  (default)"
echo "    2) Black      — pure black background, white/grey text"
echo "    3) Dark Green — dark green background, white/green text"
echo "    4) Red        — dark red background, white/pink text"
echo "    5) Orange     — dark orange background, white/amber text"
echo "    6) Yellow     — dark yellow background, white/yellow text"
echo "    7) White      — light grey background, dark text (icon badge enabled)"
echo ""
read -rp "  Theme [1]: " THEME_NUM
THEME_NUM="${THEME_NUM:-1}"

case "$THEME_NUM" in
  1) THEME_NAME="dark_blue"  ;;
  2) THEME_NAME="black"      ;;
  3) THEME_NAME="dark_green" ;;
  4) THEME_NAME="red"        ;;
  5) THEME_NAME="orange"     ;;
  6) THEME_NAME="yellow"     ;;
  7) THEME_NAME="white"      ;;
  *) warn "Invalid choice — keeping current theme."; exit 0 ;;
esac

# ── Update only the theme line in the config ──────────────────────────────────
if grep -qE "^\s*theme\s*=" "$CFG_FILE"; then
  # Replace existing theme line
  sed -i "s|^\s*theme\s*=.*|theme = ${THEME_NAME}|" "$CFG_FILE"
else
  # Add [colours] section and theme if missing
  if grep -q "^\[colours\]" "$CFG_FILE"; then
    # Section exists but no theme line — append after [colours]
    sed -i "/^\[colours\]/a theme = ${THEME_NAME}" "$CFG_FILE"
  else
    # No section at all — append both
    printf '\n[colours]\ntheme = %s\n' "$THEME_NAME" >> "$CFG_FILE"
  fi
fi

# Fix ownership if run with sudo
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
  chown "$SUDO_USER:$SUDO_USER" "$CFG_FILE"
fi

ok "Theme changed to: $THEME_NAME"

# ── Restart the service ───────────────────────────────────────────────────────
if systemctl is-active rpi-clock &>/dev/null; then
  echo ""
  echo "  Restarting rpi-clock service..."
  sudo systemctl restart rpi-clock
  ok "Service restarted — new theme active."
elif systemctl is-enabled rpi-clock &>/dev/null; then
  sudo systemctl start rpi-clock
  ok "Service started."
fi

echo ""
echo -e "${GRN}=============================================================${NC}"
echo -e "${GRN}  ✅  Theme updated${NC}"
echo -e "${GRN}=============================================================${NC}"
echo ""
