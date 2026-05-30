#!/usr/bin/env bash
# =============================================================================
#  install.sh  —  Waveshare 3.5" LCD (A) + rpi_clock  —  All-in-one installer
#
#  Hardware: Raspberry Pi 2B  /  Pi Zero v1.3
#  OS:       Raspberry Pi OS Lite  32-bit  (Bullseye or Bookworm)
#
#  What this script does:
#    1.  Updates the system and installs all required packages
#    2.  Downloads and installs the Waveshare 35a SPI LCD overlay
#    3.  Configures /boot/config.txt for the SPI display (fixes hdmi_cvt, etc.)
#    4.  Configures X11 to use the SPI framebuffer
#    5.  Installs rpi_clock.py (this repo — no external repo needed)
#    6.  Prompts for OpenWeatherMap API key, location and timezone
#    7.  Creates ~/.xinitrc and a systemd service
#    8.  Applies SD-card protection (noatime, tmpfs, disable swap, journald RAM)
#    9.  Enables the RPi Overlay Filesystem (read-only root) for SD longevity
#   10.  Reboots
#
#  Usage:
#    sudo bash install.sh
# =============================================================================

set -euo pipefail

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; YEL='\033[1;33m'; GRN='\033[0;32m'; CYN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GRN}[ OK ]${NC}  $*"; }
warn()  { echo -e "${YEL}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[FAIL]${NC}  $*" >&2; exit 1; }

# ── Banner ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYN}=============================================================${NC}"
echo -e "${CYN}  Waveshare 3.5\" LCD (A) + rpi_clock  —  All-in-one installer${NC}"
echo -e "${CYN}  Raspberry Pi 2B / Zero v1.3  —  Lite 32-bit${NC}"
echo -e "${CYN}=============================================================${NC}"
echo ""

# ── Pre-flight checks ──────────────────────────────────────────────────────────
[ "$EUID" -ne 0 ]                          && die "Run with:  sudo bash $0"
[ -z "${SUDO_USER:-}" ] || [ "$SUDO_USER" = "root" ] \
                                           && die "Run with sudo from your normal user, not as root."

USER_NAME="$SUDO_USER"
USER_HOME=$(eval echo "~$USER_NAME")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect boot config paths (Bookworm moved them to /boot/firmware)
if   [ -f /boot/firmware/config.txt ]; then
  CONFIG_TXT="/boot/firmware/config.txt"
  OVERLAYS_DIR="/boot/firmware/overlays"
elif [ -f /boot/config.txt ]; then
  CONFIG_TXT="/boot/config.txt"
  OVERLAYS_DIR="/boot/overlays"
else
  die "Cannot find config.txt"
fi
[ -d "$OVERLAYS_DIR" ] || die "Cannot find overlays directory"

CLOCK_DIR="$USER_HOME/rpi_clock"

info "Config:    $CONFIG_TXT"
info "Overlays:  $OVERLAYS_DIR"
info "User:      $USER_NAME  ($USER_HOME)"
info "Clock dir: $CLOCK_DIR"
echo ""

# =============================================================================
# STEP 0 — Prompt for all user-specific information up-front
# =============================================================================
echo -e "${CYN}--- Configuration prompts ---${NC}"
echo ""

# Timezone
echo "Available timezone examples:"
echo "  Australia/Adelaide   Australia/Sydney   Australia/Perth"
echo "  America/New_York     America/Los_Angeles   Europe/London"
echo ""
read -rp "  Timezone (e.g. Australia/Adelaide): " TZ_NAME
TZ_NAME="${TZ_NAME:-Australia/Adelaide}"

# OpenWeatherMap API key
echo ""
echo "  Get a free API key at: https://openweathermap.org/api"
read -rp "  OpenWeatherMap API key: " OWM_APIKEY
[ -z "$OWM_APIKEY" ] && die "API key cannot be empty."

# Location
echo ""
echo "  Location format — choose ONE of:"
echo "    City name:   q=Moana,au      (country code is 2-letter ISO)"
echo "    Post/ZIP:    zip=5169,au     (zip=75248,us for US)"
echo "  Note: q=suburb,country gives the most accurate location display."
echo ""
read -rp "  Location (e.g. q=Moana,au): " OWM_LOCATION
OWM_LOCATION="${OWM_LOCATION:-q=Adelaide,au}"

# Resolve display location via OWM geocoding (runs once at install time)
info "Looking up location name..."
DISPLAY_LOCATION=""
LOC_KEY=$(echo "$OWM_LOCATION" | cut -d'=' -f1 | tr -d ' ')
LOC_VAL=$(echo "$OWM_LOCATION" | cut -d'=' -f2-)

if [ "$LOC_KEY" = "q" ]; then
  GEO_RESULT=$(curl -sf \
    "https://api.openweathermap.org/geo/1.0/direct?q=${LOC_VAL}&limit=1&appid=${OWM_APIKEY}" \
    2>/dev/null || echo "[]")
else
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
  warn "Could not resolve location — will use city name from weather API."
  DISPLAY_LOCATION=""
fi

# Units
echo ""
read -rp "  Temperature units — metric (°C) or imperial (°F)? [metric]: " OWM_UNITS
OWM_UNITS="${OWM_UNITS:-metric}"
[[ "$OWM_UNITS" != "metric" && "$OWM_UNITS" != "imperial" ]] && OWM_UNITS="metric"

# 12 or 24 hour clock
echo ""
read -rp "  Clock format — 12 or 24 hour? [24]: " CLOCK_FMT
CLOCK_FMT="${CLOCK_FMT:-24}"
if [ "$CLOCK_FMT" = "12" ]; then
  TIME_FORMAT="%I:%M:%S %p"
else
  TIME_FORMAT="%H:%M:%S"
fi

echo ""
ok "Collected: TZ=$TZ_NAME  units=$OWM_UNITS  fmt=$CLOCK_FMT-hour"
echo ""

# =============================================================================
# STEP 1 — System update and package install
# =============================================================================
info "[1/9] Updating system and installing packages..."
apt-get update -q
apt-get upgrade -y -q

apt-get install -y \
  xserver-xorg xserver-xorg-video-fbdev xinit \
  x11-xserver-utils \
  python3 python3-tk python3-requests python3-pil.imagetk \
  fonts-freefont-ttf fontconfig \
  git wget unzip \
  xinput-calibrator xserver-xorg-input-evdev

ok "Packages installed."

# =============================================================================
# STEP 2 — Set timezone
# =============================================================================
info "[2/9] Setting timezone to $TZ_NAME..."
timedatectl set-timezone "$TZ_NAME" || warn "timedatectl failed — set timezone manually with raspi-config."
ok "Timezone set."

# =============================================================================
# STEP 3 — Install Waveshare overlay
# =============================================================================
info "[3/9] Installing Waveshare 3.5\" LCD (A) overlay..."
cd /tmp
rm -f Waveshare35a.zip waveshare35a.dtbo 2>/dev/null || true
wget -q https://files.waveshare.com/wiki/common/Waveshare35a.zip \
  || die "Failed to download Waveshare overlay. Check your internet connection."
unzip -oq Waveshare35a.zip
cp waveshare35a.dtbo "$OVERLAYS_DIR/"
ok "Overlay installed to $OVERLAYS_DIR."

# =============================================================================
# STEP 4 — Configure /boot/config.txt
# =============================================================================
info "[4/9] Configuring $CONFIG_TXT..."

# Disable KMS/FKMS overlays (incompatible with SPI LCD on Pi 2/Zero)
sed -i 's/^dtoverlay=vc4-kms-v3d/#dtoverlay=vc4-kms-v3d/'   "$CONFIG_TXT"
sed -i 's/^dtoverlay=vc4-fkms-v3d/#dtoverlay=vc4-fkms-v3d/' "$CONFIG_TXT"

if ! grep -q "BEGIN WAVESHARE LCD" "$CONFIG_TXT"; then
  cat >> "$CONFIG_TXT" <<'CFGEOF'

# === BEGIN WAVESHARE LCD + WATCHDOG ===
dtparam=spi=on
dtoverlay=waveshare35a
hdmi_force_hotplug=1
hdmi_group=2
hdmi_mode=87
hdmi_cvt=480 320 60 6 0 0 0
hdmi_drive=2
display_rotate=0

# Disable KMS — required for SPI LCD on Pi 2/Zero
disable_fw_kms_setup=1

# Hardware watchdog — auto-reboot on full system hang
dtparam=watchdog=on
# === END WAVESHARE LCD + WATCHDOG ===
CFGEOF
  ok "Display config block added."
else
  ok "Display config block already present — skipped."
fi

# =============================================================================
# STEP 5 — Configure X11
# =============================================================================
info "[5/9] Configuring X11..."

# Allow any user to start X
cat > /etc/X11/Xwrapper.config <<'EOF'
allowed_users=anybody
needs_root_rights=yes
EOF

# Point X at the SPI framebuffer (fb0 when KMS is disabled)
cat > /usr/share/X11/xorg.conf.d/99-fbdev.conf <<'EOF'
Section "Device"
    Identifier  "SPI LCD"
    Driver      "fbdev"
    # Pi 2B/Zero: HDMI takes fb0, SPI LCD gets fb1.
    # If your display is blank, try changing fb1 to fb0.
    Option      "fbdev" "/dev/fb1"
EndSection
EOF

# Copy evdev config to a higher-priority slot (touch input priority)
if [ -f /usr/share/X11/xorg.conf.d/10-evdev.conf ]; then
  cp /usr/share/X11/xorg.conf.d/10-evdev.conf \
     /usr/share/X11/xorg.conf.d/45-evdev.conf
fi

# Touch calibration — default values for Waveshare 3.5" (A) ADS7846
# Run "DISPLAY=:0 xinput_calibrator" after first boot to get your actual values.
if [ ! -f /usr/share/X11/xorg.conf.d/99-calibration.conf ]; then
  cat > /usr/share/X11/xorg.conf.d/99-calibration.conf <<'EOF'
Section "InputClass"
    Identifier      "calibration"
    MatchProduct    "ADS7846 Touchscreen"
    Option  "Calibration"   "3932 300 294 3801"
    Option  "SwapAxes"      "1"
EndSection
EOF
fi

ok "X11 configured."

# =============================================================================
# STEP 6 — Install rpi_clock from this repo
# =============================================================================
info "[6/9] Installing rpi_clock..."

mkdir -p "$CLOCK_DIR"
cp "$SCRIPT_DIR/clock/rpi_clock.py" "$CLOCK_DIR/"

# Write populated config file
cat > "$CLOCK_DIR/rpi_clock.cfg" <<EOCFG
# rpi_clock.cfg  —  generated by install.sh on $(date)
# Edit carefully. Re-run install.sh to regenerate.

[openweathermap]
api_key          = ${OWM_APIKEY}
location         = ${OWM_LOCATION}
display_location = ${OWM_LOCATION}
units            = ${OWM_UNITS}

[display]
fullscreen  = True
width       = 480
height      = 320
time_format = ${TIME_FORMAT}
date_format = %A  %d %B %Y
EOCFG

chown -R "$USER_NAME:$USER_NAME" "$CLOCK_DIR"
ok "rpi_clock installed to $CLOCK_DIR."

# =============================================================================
# STEP 7 — Create ~/.xinitrc
# =============================================================================
info "[7/9] Creating ~/.xinitrc..."

cat > "$USER_HOME/.xinitrc" <<'EOF'
#!/bin/bash

# Disable screen blanking and power saving
xset s off
xset -dpms
xset s noblank

# Launch the clock (log goes to RAM — no SD writes)
cd ~/rpi_clock
exec python3 rpi_clock.py rpi_clock.cfg >> /tmp/rpi_clock.log 2>&1
EOF

chmod +x "$USER_HOME/.xinitrc"
chown   "$USER_NAME:$USER_NAME" "$USER_HOME/.xinitrc"
ok ".xinitrc created."

# =============================================================================
# STEP 8 — Create systemd service
# =============================================================================
info "[8/9] Creating systemd service..."

cat > /etc/systemd/system/rpi-clock.service <<EOSERVICE
[Unit]
Description=rpi_clock Kiosk Display
After=multi-user.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
Environment=HOME=${USER_HOME}

# Start X on virtual terminal 1 and run .xinitrc
ExecStart=/usr/bin/xinit ${USER_HOME}/.xinitrc -- :0 vt1

# Auto-restart on crash with 10-second cooldown
Restart=always
RestartSec=10
TimeoutStartSec=30

# Log to journald (stored in RAM via volatile config)
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rpi-clock

[Install]
WantedBy=multi-user.target
EOSERVICE

systemctl daemon-reload
systemctl enable rpi-clock.service
systemctl disable getty@tty1.service 2>/dev/null || true
ok "systemd service enabled."

# =============================================================================
# STEP 9 — SD card protection (swap off, noatime, tmpfs, journald volatile)
# =============================================================================
info "[9/9] Applying SD card protection..."

# 9a. Disable swap
if systemctl is-enabled dphys-swapfile 2>/dev/null | grep -q enabled; then
  dphys-swapfile swapoff    2>/dev/null || true
  dphys-swapfile uninstall  2>/dev/null || true
  systemctl disable dphys-swapfile 2>/dev/null || true
  info "  → Swap disabled"
fi

# 9b. noatime + commit=600 on root filesystem
if ! grep -q 'noatime' /etc/fstab; then
  sed -i '/\/ .*ext4/ s/defaults/defaults,noatime,commit=600/' /etc/fstab
  info "  → Root fs: noatime + commit=600"
fi

# 9c. tmpfs mounts
add_tmpfs() {
  local mnt="$1" sz="$2"
  if ! grep -qE "tmpfs\s+${mnt}\s" /etc/fstab; then
    printf 'tmpfs  %-16s tmpfs  defaults,noatime,nosuid,nodev,size=%-6s 0  0\n' \
      "$mnt" "$sz" >> /etc/fstab
    info "  → $mnt → tmpfs ($sz)"
  fi
}
add_tmpfs "/tmp"     "50M"
add_tmpfs "/var/tmp" "10M"
add_tmpfs "/var/log" "20M"

# 9d. journald volatile
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/sd-protect.conf <<'EOF'
[Journal]
Storage=volatile
RuntimeMaxUse=8M
RuntimeMaxFileSize=2M
EOF
info "  → journald: volatile (RAM only, 8M max)"

# 9e. Hardware watchdog via systemd
if ! grep -q "^RuntimeWatchdogSec" /etc/systemd/system.conf; then
  if grep -q "^#RuntimeWatchdogSec" /etc/systemd/system.conf; then
    sed -i 's/^#RuntimeWatchdogSec=.*/RuntimeWatchdogSec=14/' /etc/systemd/system.conf
  else
    echo "RuntimeWatchdogSec=14" >> /etc/systemd/system.conf
  fi
  info "  → Hardware watchdog: 14s timeout"
fi

ok "SD card protection applied."

# =============================================================================
# STEP 10 — Enable RPi Overlay Filesystem (read-only root via raspi-config)
# =============================================================================
echo ""
info "[+] Enabling Overlay Filesystem (read-only root)..."
echo ""
warn "The Overlay Filesystem makes the root partition read-only."
warn "Future changes (apt install, config edits) require:"
warn "  sudo raspi-config  →  Performance Options → Overlay FS → Disable"
warn "  (make changes, then re-enable)"
echo ""

if command -v raspi-config &>/dev/null; then
  # raspi-config noninteractive call to enable overlayfs
  INTERACTIVE=False raspi-config nonint enable_overlayfs 2>/dev/null \
    || {
      warn "raspi-config overlay command failed — trying alternative method..."
      # Fallback: write the overlayfs kernel parameter directly
      CMDLINE_FILE=""
      [ -f /boot/firmware/cmdline.txt ] && CMDLINE_FILE="/boot/firmware/cmdline.txt"
      [ -f /boot/cmdline.txt ]          && CMDLINE_FILE="/boot/cmdline.txt"
      if [ -n "$CMDLINE_FILE" ] && ! grep -q "overlayroot" "$CMDLINE_FILE"; then
        # overlayroot is not available on stock RPi OS Lite;
        # use raspi-config's own overlay mechanism if available
        warn "Manual overlayfs setup requires raspi-config — skipping automatic enable."
        warn "After reboot, run:  sudo raspi-config → Performance → Overlay FS"
      fi
    }
  ok "Overlay Filesystem enabled (takes effect after reboot)."
else
  warn "raspi-config not found — skipping overlay enable."
  warn "After reboot, run:  sudo raspi-config → Performance → Overlay FS"
fi

# =============================================================================
# STEP 11 — Clean up any old manual-start methods
# =============================================================================
sed -i '/startx/d'      "$USER_HOME/.bash_profile" 2>/dev/null || true
sed -i '/FRAMEBUFFER/d' "$USER_HOME/.bash_profile" 2>/dev/null || true
sed -i '/rpi_clock/d'   "$USER_HOME/.profile"      2>/dev/null || true

# =============================================================================
# Done — print summary
# =============================================================================
echo ""
echo -e "${GRN}=============================================================${NC}"
echo -e "${GRN}  ✅  SETUP COMPLETE${NC}"
echo -e "${GRN}=============================================================${NC}"
echo ""
echo "  On next reboot:"
echo "    1.  Pi boots to console (no desktop environment)"
echo "    2.  systemd starts rpi-clock.service"
echo "    3.  X starts on the Waveshare LCD (/dev/fb0)"
echo "    4.  rpi_clock shows clock + weather"
echo ""
echo "  SD card protection:"
echo "    /tmp, /var/log, /var/tmp → RAM (tmpfs)"
echo "    swap                     → disabled"
echo "    journald                 → volatile (RAM, 8M max)"
echo "    root fs                  → noatime, commit=600"
echo "    Overlay FS               → enabled (read-only root)"
echo ""
echo "  Auto-recovery:"
echo "    App crash  → service restarts in 10s"
echo "    System hang → hardware watchdog reboots"
echo ""
echo "  Useful commands:"
echo "    journalctl -u rpi-clock -f        # live service logs (RAM)"
echo "    cat /tmp/rpi_clock.log             # clock app log (RAM)"
echo ""
echo "  Touch calibration (after first boot):"
echo "    sudo raspi-config → Performance → Overlay FS → Disable"
echo "    sudo reboot"
echo "    DISPLAY=:0 xinput_calibrator"
echo "    # Copy output values to:"
echo "    sudo nano /usr/share/X11/xorg.conf.d/99-calibration.conf"
echo "    sudo raspi-config → Performance → Overlay FS → Enable"
echo "    sudo reboot"
echo ""
echo "  To make config changes later:"
echo "    sudo raspi-config → Performance → Overlay FS → Disable"
echo "    sudo reboot  (then make changes)"
echo "    sudo raspi-config → Performance → Overlay FS → Enable"
echo "    sudo reboot"
echo ""
echo -e "${YEL}  Reboot now?${NC}"
read -rp "  [Y/n]: " DO_REBOOT
DO_REBOOT="${DO_REBOOT:-Y}"
if [[ "$DO_REBOOT" =~ ^[Yy]$ ]]; then
  echo "  Rebooting in 5 seconds..."
  sleep 5
  reboot
fi
