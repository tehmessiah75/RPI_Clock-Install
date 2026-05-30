# RPi Clock — Waveshare 3.5" LCD (A)

A fully self-contained Raspberry Pi clock + weather display for the
**Waveshare 3.5" LCD (A)** on a **Raspberry Pi 2B** or **Pi Zero v1.3**.

- Large time display with date
- Live weather from [OpenWeatherMap](https://openweathermap.org/api) (free tier)
- Temperature, feels-like, humidity, wind, daily min/max
- Fully offline after first data fetch (keeps showing last known weather)
- Single bash script installs and configures everything
- SD card protected by RPi Overlay Filesystem (read-only root)
- Auto-restarts on crash; hardware watchdog reboots on full hang

> **No external repos required.** This is a complete, standalone replacement
> for the archived [texadactyl/rpi_clock](https://github.com/texadactyl/rpi_clock) project.

---

## Hardware

| Item | Notes |
|------|-------|
| Raspberry Pi 2 Model B *or* Pi Zero v1.3 | Other Pi models will work but are untested |
| [Waveshare 3.5" RPi LCD (A)](https://www.waveshare.com/wiki/3.5inch_RPi_LCD_(A)) | SPI interface, 480×320, ADS7846 touch controller |
| MicroSD card, 8 GB or larger | Class 10 / A1 recommended |
| Power supply | 5V 2A micro-USB |
| Internet connection (Wi-Fi or Ethernet) | Required during setup and for weather updates |

---

## Part 1 — Write the SD card

Do this on your PC/Mac **before** inserting the card into the Pi.

### 1.1 Download Raspberry Pi Imager

<https://www.raspberrypi.com/software/>

### 1.2 Flash the image

1. Open Raspberry Pi Imager.
2. **Choose Device** → Raspberry Pi 2 (or Pi Zero).
3. **Choose OS** → *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite (32-bit)**.
4. **Choose Storage** → your SD card.
5. Click **Next** → **Edit Settings** (the gear icon).

### 1.3 Pre-configure in Imager (important — saves a monitor/keyboard)

In the *OS Customisation* screen:

| Setting | Value |
|---------|-------|
| Hostname | `rpi-clock` (or anything you like) |
| Username | `pi` (or your preferred username) |
| Password | choose a strong password |
| Wi-Fi SSID | your network name |
| Wi-Fi password | your network password |
| Wi-Fi country | your 2-letter country code (e.g. `AU`) |
| Locale / timezone | set your timezone now |
| Enable SSH | ✅ tick this |

Click **Save** → **Yes** → let it flash and verify.

### 1.4 Insert card, connect Pi, power on

- Attach the Waveshare display to the Pi's GPIO header.
- Insert the SD card.
- Power on.
- Wait ~60 seconds for first boot.
- Find the Pi's IP address from your router, then SSH in:

```bash
ssh pi@rpi-clock.local
# or
ssh pi@<IP address>
```

---

## Part 2 — Run the installer

All remaining setup is done by a single script on the Pi.

### 2.1 Install git

Git is not pre-installed on Raspberry Pi OS Lite. Install it first:

```bash
sudo apt-get install -y git
```

### 2.2 Clone this repo

```bash
git clone https://github.com/tehmessiah75/RPI_Clock-Install.git
cd RPI_Clock-Install
```

### 2.3 Run the installer

```bash
sudo bash install.sh
```

The script will prompt you for:

| Prompt | Example |
|--------|---------|
| Timezone | `Australia/Adelaide` |
| OpenWeatherMap API key | `abc123...` (free at openweathermap.org) |
| Location | `q=Adelaide,au` or `zip=5000,au` |
| Units | `metric` or `imperial` |
| Clock format | `24` or `12` |

> **Get a free OpenWeatherMap API key** at <https://openweathermap.org/api>.
> The free "Current Weather Data" plan is all that's needed.
> New keys can take up to 2 hours to activate.

The installer will then (without further prompts):

1. Update the system and install packages
2. Set your timezone
3. Download and install the Waveshare SPI overlay
4. Configure `/boot/config.txt`
5. Configure X11 for the SPI framebuffer
6. Install `rpi_clock.py` and write your config
7. Create `~/.xinitrc` and a systemd service
8. Apply SD card protection (tmpfs, noatime, disable swap, journald to RAM)
9. Enable the RPi Overlay Filesystem (read-only root)
10. Ask if you want to reboot now

---

## Part 3 — After first boot

Once the Pi reboots, the clock should start automatically on the LCD.

### Check the service status

```bash
systemctl status rpi-clock
journalctl -u rpi-clock -f
```

### Check the clock app log

```bash
cat /tmp/rpi_clock.log
```

(This is in RAM — it disappears on reboot. That's intentional — no SD writes.)

---

## Part 4 — Touch calibration

The default calibration values work for most Waveshare 3.5" (A) displays, but
if your touch is off you can recalibrate.

Because the Overlay Filesystem makes the root read-only, you need to
temporarily disable it:

```bash
sudo raspi-config
# Performance Options → Overlay File System → No (disable)
# Then: Would you like the boot partition to be write-protected? → No
sudo reboot
```

After reboot (now read-write):

```bash
DISPLAY=:0 xinput_calibrator
```

Touch all four corners as instructed. Copy the four numbers from the output,
then update the calibration file:

```bash
sudo nano /usr/share/X11/xorg.conf.d/99-calibration.conf
# Replace the Calibration line values with your new numbers
```

Re-enable the Overlay Filesystem:

```bash
sudo raspi-config
# Performance Options → Overlay File System → Yes (enable)
sudo reboot
```

---

## Making changes after install

Because the Overlay Filesystem makes the root read-only, **any change you want
to persist** (editing the config, running apt, etc.) requires:

```bash
# 1. Disable overlay (makes root writable again)
sudo raspi-config
# Performance Options → Overlay File System → No

# 2. Reboot into writable mode
sudo reboot

# 3. Make your changes, e.g.:
nano ~/rpi_clock/rpi_clock.cfg
# or: sudo apt install <something>

# 4. Re-enable overlay
sudo raspi-config
# Performance Options → Overlay File System → Yes

# 5. Reboot
sudo reboot
```

### Editing the clock config only

```bash
nano ~/rpi_clock/rpi_clock.cfg
sudo systemctl restart rpi-clock
```

Config options:

| Key | Description | Example |
|-----|-------------|---------|
| `api_key` | OpenWeatherMap API key | `abc123...` |
| `location` | City or ZIP query | `q=Adelaide,au` |
| `units` | `metric` or `imperial` | `metric` |
| `fullscreen` | `True` / `False` | `True` |
| `width` / `height` | Screen resolution | `480` / `320` |
| `time_format` | strftime format | `%H:%M:%S` |
| `date_format` | strftime format | `%A  %d %B %Y` |

---

## SD card protection — what's enabled

| Protection | Method |
|-----------|--------|
| Read-only root filesystem | RPi Overlay FS |
| No swap | `dphys-swapfile` disabled |
| `/tmp`, `/var/log`, `/var/tmp` in RAM | `tmpfs` mounts |
| Reduced inode writes | `noatime`, `commit=600` on root |
| System logs in RAM only | `journald` volatile, 8 MB cap |
| Auto-reboot on full hang | Hardware watchdog, 14s timeout |

---

## Troubleshooting

### Black screen after reboot

- SSH in and check: `journalctl -u rpi-clock -f`
- Verify the overlay was copied: `ls /boot/overlays/waveshare35a.dtbo`
- Verify the config block: `grep -A20 "BEGIN WAVESHARE" /boot/config.txt`
- Check X is starting: `ps aux | grep xinit`

### Weather shows "Unavailable"

- Check internet: `ping -c3 api.openweathermap.org`
- Verify your API key is correct in `~/rpi_clock/rpi_clock.cfg`
- New OWM keys can take up to 2 hours to activate
- Check the clock log: `cat /tmp/rpi_clock.log`

### Touch not working

- Check the device exists: `ls /dev/input/event*`
- Run calibrator: `DISPLAY=:0 xinput_calibrator`
- See [Part 4 — Touch calibration](#part-4--touch-calibration) above

### Screen is portrait / rotated wrong

Edit `/boot/config.txt` (disable overlay first):

```
display_rotate=0    # Normal landscape
display_rotate=1    # 90° clockwise
display_rotate=2    # 180°
display_rotate=3    # 90° counter-clockwise
```

---

## File structure

```
rpi_clock_waveshare/
├── install.sh          ← Run this: sudo bash install.sh
├── clock/
│   ├── rpi_clock.py    ← Python clock application (standalone)
│   └── rpi_clock.cfg   ← Default config template (populated by installer)
└── README.md
```

---

## Acknowledgements

Inspired by the original [texadactyl/rpi_clock](https://github.com/texadactyl/rpi_clock)
(archived July 2024). This project is a complete rewrite with no dependency on
that repository.

Weather data from [OpenWeatherMap](https://openweathermap.org).

---

## Licence

GNU General Public License v3.0 — see [LICENSE](LICENSE).
