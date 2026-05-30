#!/usr/bin/env bash
# =============================================================================
#  configure.sh  —  Reconfigure rpi_clock settings
#
#  Run this any time you want to change:
#    - OpenWeatherMap API key
#    - Location
#    - Temperature units
#    - Clock format (12/24 hour)
#    - Timezone
#    - Colour theme
#
#  Usage:
#    bash configure.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; YEL='\033[1;33m'; GRN='\033[0;32m'; CYN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GRN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YEL}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[FAIL]${NC}  $*" >&2; exit 1; }

# ── Find the clock directory ──────────────────────────────────────────────────
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
  TARGET_USER="$SUDO_USER"
else
  TARGET_USER="$USER"
fi
TARGET_HOME=$(eval echo "~$TARGET_USER")
CFG_FILE="$TARGET_HOME/rpi_clock/rpi_clock.cfg"

echo ""
echo -e "${CYN}=============================================================${NC}"
echo -e "${CYN}  rpi_clock  —  Reconfigure${NC}"
echo -e "${CYN}=============================================================${NC}"
echo ""

# ── Show current settings ─────────────────────────────────────────────────────
if [ -f "$CFG_FILE" ]; then
  echo -e "${YEL}Current settings:${NC}"
  grep -E "^(api_key|location|units|time_format|theme)" "$CFG_FILE" \
    | sed 's/^/  /' || true
  echo ""
fi

# ── Timezone ──────────────────────────────────────────────────────────────────
echo "Timezone examples:"
echo "  Australia/Adelaide   Australia/Sydney   Australia/Perth"
echo "  America/New_York     America/Los_Angeles   Europe/London"
echo ""
CURRENT_TZ=$(timedatectl show --property=Timezone --value 2>/dev/null \
             || echo "Australia/Adelaide")
read -rp "  Timezone [${CURRENT_TZ}]: " TZ_NAME
TZ_NAME="${TZ_NAME:-$CURRENT_TZ}"

# ── OpenWeatherMap API key ─────────────────────────────────────────────────────
echo ""
echo "  Get a free API key at: https://openweathermap.org/api"
read -rp "  OpenWeatherMap API key: " OWM_APIKEY
[ -z "$OWM_APIKEY" ] && die "API key cannot be empty."

# ── Location ──────────────────────────────────────────────────────────────────
echo ""
echo "  Location format — choose ONE of:"
echo "    City name:   q=Moana,au      (country code is 2-letter ISO)"
echo "    Post/ZIP:    zip=5169,au     (zip=75248,us for US)"
echo "  Note: q=suburb,country gives the most accurate location display."
echo ""
read -rp "  Location (e.g. q=Moana,au): " OWM_LOCATION
OWM_LOCATION="${OWM_LOCATION:-q=Adelaide,au}"

# ── Resolve display location string via OWM geocoding ─────────────────────────
info "Looking up location name..."
DISPLAY_LOCATION=""

# Extract key and value from location string
LOC_KEY=$(echo "$OWM_LOCATION" | cut -d'=' -f1 | tr -d ' ')
LOC_VAL=$(echo "$OWM_LOCATION" | cut -d'=' -f2-)

if [ "$LOC_KEY" = "q" ]; then
  # Forward geocoding
  GEO_RESULT=$(curl -sf \
    "https://api.openweathermap.org/geo/1.0/direct?q=${LOC_VAL}&limit=1&appid=${OWM_APIKEY}" \
    2>/dev/null || echo "[]")
else
  # Get coordinates from weather API first, then reverse geocode
  WEATHER_RESULT=$(curl -sf \
    "https://api.openweathermap.org/data/2.5/weather?${OWM_LOCATION}&appid=${OWM_APIKEY}&units=metric" \
    2>/dev/null || echo "{}")
  LAT=$(echo "$WEATHER_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('coord',{}).get('lat',''))" 2>/dev/null)
  LON=$(echo "$WEATHER_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('coord',{}).get('lon',''))" 2>/dev/null)
  if [ -n "$LAT" ] && [ -n "$LON" ]; then
    GEO_RESULT=$(curl -sf \
      "https://api.openweathermap.org/geo/1.0/reverse?lat=${LAT}&lon=${LON}&limit=1&appid=${OWM_APIKEY}" \
      2>/dev/null || echo "[]")
  else
    GEO_RESULT="[]"
  fi
fi

# Parse the geo result
DISPLAY_LOCATION=$(echo "$GEO_RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data:
        g = data[0]
        city    = g.get('name', '')
        state   = g.get('state', '')
        country = g.get('country', '')
        AU = {'new south wales':'NSW','victoria':'VIC','queensland':'QLD',
              'south australia':'SA','western australia':'WA','tasmania':'TAS',
              'northern territory':'NT','australian capital territory':'ACT'}
        US = {'alabama':'AL','alaska':'AK','arizona':'AZ','arkansas':'AR',
              'california':'CA','colorado':'CO','connecticut':'CT','delaware':'DE',
              'florida':'FL','georgia':'GA','hawaii':'HI','idaho':'ID',
              'illinois':'IL','indiana':'IN','iowa':'IA','kansas':'KS',
              'kentucky':'KY','louisiana':'LA','maine':'ME','maryland':'MD',
              'massachusetts':'MA','michigan':'MI','minnesota':'MN',
              'mississippi':'MS','missouri':'MO','montana':'MT','nebraska':'NE',
              'nevada':'NV','new hampshire':'NH','new jersey':'NJ',
              'new mexico':'NM','new york':'NY','north carolina':'NC',
              'north dakota':'ND','ohio':'OH','oklahoma':'OK','oregon':'OR',
              'pennsylvania':'PA','rhode island':'RI','south carolina':'SC',
              'south dakota':'SD','tennessee':'TN','texas':'TX','utah':'UT',
              'vermont':'VT','virginia':'VA','washington':'WA',
              'west virginia':'WV','wisconsin':'WI','wyoming':'WY'}
        if country == 'AU':
            state = AU.get(state.lower(), state)
        elif country == 'US':
            state = US.get(state.lower(), state)
        parts = [p for p in [city, state, country] if p]
        print(', '.join(parts))
    else:
        print('')
except:
    print('')
" 2>/dev/null)

if [ -n "$DISPLAY_LOCATION" ]; then
  ok "Location resolved: $DISPLAY_LOCATION"
else
  warn "Could not resolve location name — will show city from weather API."
  DISPLAY_LOCATION=""
fi

# ── Units ─────────────────────────────────────────────────────────────────────
echo ""
read -rp "  Temperature units — metric (°C) or imperial (°F)? [metric]: " OWM_UNITS
OWM_UNITS="${OWM_UNITS:-metric}"
[[ "$OWM_UNITS" != "metric" && "$OWM_UNITS" != "imperial" ]] && OWM_UNITS="metric"

# ── Clock format ──────────────────────────────────────────────────────────────
echo ""
read -rp "  Clock format — 12 or 24 hour? [24]: " CLOCK_FMT
CLOCK_FMT="${CLOCK_FMT:-24}"
if [ "$CLOCK_FMT" = "12" ]; then
  TIME_FORMAT="%I:%M:%S %p"
else
  TIME_FORMAT="%H:%M:%S"
fi

# ── Theme selection ───────────────────────────────────────────────────────────
echo ""
echo "  Select a colour theme:"
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
  *) warn "Invalid choice — using Dark Blue."; THEME_NAME="dark_blue" ;;
esac

echo ""
ok "Settings: TZ=$TZ_NAME  location=$OWM_LOCATION  units=$OWM_UNITS  fmt=$CLOCK_FMT-hour  theme=$THEME_NAME"
echo ""

# ── Apply timezone ────────────────────────────────────────────────────────────
if command -v timedatectl &>/dev/null; then
  sudo timedatectl set-timezone "$TZ_NAME" 2>/dev/null \
    && info "Timezone set to $TZ_NAME" \
    || warn "Could not set timezone — set it manually with raspi-config"
fi

# ── Write config file ─────────────────────────────────────────────────────────
mkdir -p "$(dirname "$CFG_FILE")"

cat > "$CFG_FILE" <<EOCFG
# rpi_clock.cfg  —  generated by configure.sh on $(date)
# Re-run configure.sh to change these settings.

[openweathermap]
api_key          = ${OWM_APIKEY}
location         = ${OWM_LOCATION}
display_location = ${DISPLAY_LOCATION}
units            = ${OWM_UNITS}

[display]
fullscreen  = True
width       = 480
height      = 320
time_format = ${TIME_FORMAT}
date_format = %A  %d %B %Y

[colours]
# Theme options: dark_blue, black, dark_green, red, orange, yellow, white
theme = ${THEME_NAME}
EOCFG

# Fix ownership if run with sudo
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
  chown "$SUDO_USER:$SUDO_USER" "$CFG_FILE"
fi

ok "Config written to $CFG_FILE"

# ── Restart the service ───────────────────────────────────────────────────────
if systemctl is-active rpi-clock &>/dev/null; then
  info "Restarting rpi-clock service..."
  sudo systemctl restart rpi-clock
  ok "Service restarted."
elif systemctl is-enabled rpi-clock &>/dev/null; then
  info "Service is enabled but not running — starting..."
  sudo systemctl start rpi-clock
  ok "Service started."
fi

echo ""
echo -e "${GRN}=============================================================${NC}"
echo -e "${GRN}  ✅  Configuration complete${NC}"
echo -e "${GRN}=============================================================${NC}"
echo ""
echo "  Config file: $CFG_FILE"
echo "  Theme:       $THEME_NAME"
echo "  To check:    journalctl -u rpi-clock -f"
echo ""
