#!/usr/bin/env python3
"""
rpi_clock.py  —  Waveshare 3.5" LCD (A) clock + weather display
Standalone replacement for the archived texadactyl/rpi_clock project.

Dependencies: tkinter (stdlib), requests (python3-requests),
              Pillow (python3-pil.imagetk)
Config file:  rpi_clock.cfg  (same directory)
"""

import tkinter as tk
import requests
import configparser
import time
import os
import sys
import logging
import io
import socket
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image, ImageTk, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("rpi_clock")


# ── Themes ────────────────────────────────────────────────────────────────────
THEMES = {
    "dark_blue": {
        "bg":        "#0a0a1a",
        "time":      "#ffffff",
        "date":      "#aaddff",
        "city":      "#88ccff",
        "ip":        "#557799",
        "temp":      "#ffdd88",
        "desc":      "#dddddd",
        "detail":    "#bbbbbb",
        "minmax":    "#aaaaaa",
        "divider":   "#223355",
        "icon_badge": False,
    },
    "black": {
        "bg":        "#000000",
        "time":      "#ffffff",
        "date":      "#cccccc",
        "city":      "#aaaaaa",
        "ip":        "#666666",
        "temp":      "#ffdd88",
        "desc":      "#dddddd",
        "detail":    "#bbbbbb",
        "minmax":    "#999999",
        "divider":   "#333333",
        "icon_badge": False,
    },
    "dark_green": {
        "bg":        "#001a00",
        "time":      "#ffffff",
        "date":      "#aaffaa",
        "city":      "#88dd88",
        "ip":        "#446644",
        "temp":      "#ffdd88",
        "desc":      "#ccffcc",
        "detail":    "#aaccaa",
        "minmax":    "#88aa88",
        "divider":   "#115511",
        "icon_badge": False,
    },
    "red": {
        "bg":        "#1a0000",
        "time":      "#ffffff",
        "date":      "#ffaaaa",
        "city":      "#ff8888",
        "ip":        "#884444",
        "temp":      "#ffdd88",
        "desc":      "#ffcccc",
        "detail":    "#ffaaaa",
        "minmax":    "#dd8888",
        "divider":   "#551111",
        "icon_badge": False,
    },
    "orange": {
        "bg":        "#1a0800",
        "time":      "#ffffff",
        "date":      "#ffddaa",
        "city":      "#ffbb77",
        "ip":        "#886633",
        "temp":      "#ffee88",
        "desc":      "#ffddcc",
        "detail":    "#ffccaa",
        "minmax":    "#ddaa77",
        "divider":   "#553311",
        "icon_badge": False,
    },
    "yellow": {
        "bg":        "#1f1f00",
        "time":      "#ffffff",
        "date":      "#ffffaa",
        "city":      "#dddd77",
        "ip":        "#777733",
        "temp":      "#ffffff",
        "desc":      "#ffffcc",
        "detail":    "#ddddaa",
        "minmax":    "#bbbb88",
        "divider":   "#444400",
        "icon_badge": False,
    },
    "white": {
        "bg":        "#f0f0f0",
        "time":      "#111111",
        "date":      "#222266",
        "city":      "#333399",
        "ip":        "#888888",
        "temp":      "#993300",
        "desc":      "#222222",
        "detail":    "#444444",
        "minmax":    "#555555",
        "divider":   "#aaaacc",
        "icon_badge": True,    # dark badge behind icon for visibility
    },
}

THEME_NAMES = {
    "1": "dark_blue",
    "2": "black",
    "3": "dark_green",
    "4": "red",
    "5": "orange",
    "6": "yellow",
    "7": "white",
}

# Australian state abbreviations
AU_STATES = {
    "new south wales":       "NSW",
    "victoria":              "VIC",
    "queensland":            "QLD",
    "south australia":       "SA",
    "western australia":     "WA",
    "tasmania":              "TAS",
    "northern territory":    "NT",
    "australian capital territory": "ACT",
}

# US state abbreviations (common ones)
US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT",
    "delaware": "DE", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO",
    "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND",
    "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

# UK regions
UK_REGIONS = {
    "england": "England", "scotland": "Scotland",
    "wales": "Wales", "northern ireland": "NI",
}


def abbreviate_state(state: str, country: str) -> str:
    """Return abbreviated state/region or original if not found."""
    s = state.lower()
    if country == "AU":
        return AU_STATES.get(s, state)
    if country == "US":
        return US_STATES.get(s, state)
    if country == "GB":
        return UK_REGIONS.get(s, state)
    return state


def get_local_ip() -> str:
    """Get the primary local network IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "?.?.?.?"


# ── Config ────────────────────────────────────────────────────────────────────
def load_config(cfg_path: str) -> configparser.RawConfigParser:
    cfg = configparser.RawConfigParser()
    if not os.path.isfile(cfg_path):
        log.error("Config file not found: %s", cfg_path)
        sys.exit(1)
    cfg.read(cfg_path)
    return cfg


# ── OpenWeatherMap ────────────────────────────────────────────────────────────
OWM_URL         = "https://api.openweathermap.org/data/2.5/weather"
OWM_GEO_URL     = "https://api.openweathermap.org/geo/1.0/direct"
OWM_REVERSE_URL = "https://api.openweathermap.org/geo/1.0/reverse"
OWM_ICON_URL    = "https://openweathermap.org/img/wn/{}@2x.png"

WIND_DIRS = [
    "N", "NNE", "NE", "ENE",
    "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW",
    "W", "WNW", "NW", "NNW",
]


def deg_to_compass(deg: float) -> str:
    idx = int((deg + 11.25) / 22.5) % 16
    return WIND_DIRS[idx]


class WeatherFetcher:
    def __init__(self, api_key: str, location: str, units: str):
        self.api_key  = api_key
        self.location = location
        self.units    = units
        self._cache:       dict  = {}
        self._icon_cache:  dict  = {}
        self._geo_cache:   str   = ""
        self._last_fetch:  float = 0.0
        self._last_geo:    float = 0.0
        self.fetch_interval: int = 600
        self.geo_interval:   int = 3600   # re-check geo once per hour

    def get(self) -> dict:
        now = time.time()
        if now - self._last_fetch < self.fetch_interval and self._cache:
            return self._cache

        params = {"appid": self.api_key, "units": self.units}
        for part in self.location.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                params[k.strip()] = v.strip()

        try:
            resp = requests.get(OWM_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._cache = self._parse(data)
            self._last_fetch = now
            log.info("Weather updated: %s", self._cache.get("description", "?"))
        except Exception as exc:
            log.warning("Weather fetch failed: %s", exc)
            if not self._cache:
                self._cache = self._placeholder()

        return self._cache

    def get_location_string(self) -> str:
        """Return 'City, State, Country' using OWM reverse geocoding.
        Uses lat/lon from the weather response — works for all location
        formats (q=, zip=, id=)."""
        now = time.time()
        if self._geo_cache and (now - self._last_geo < self.geo_interval):
            return self._geo_cache

        # Need coordinates from weather cache — wait until we have them
        lat = self._cache.get("lat")
        lon = self._cache.get("lon")
        if lat is None or lon is None:
            self._geo_cache = self._cache.get("city", "")
            return self._geo_cache

        try:
            params = {"lat": lat, "lon": lon, "limit": 1, "appid": self.api_key}
            resp = requests.get(OWM_REVERSE_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if data:
                geo      = data[0]
                city     = geo.get("name", "")
                state    = geo.get("state", "")
                country  = geo.get("country", "")
                state_ab = abbreviate_state(state, country) if state else ""
                parts    = [p for p in [city, state_ab, country] if p]
                self._geo_cache = ", ".join(parts)
                self._last_geo  = now
                log.info("Location: %s", self._geo_cache)
            else:
                self._geo_cache = self._cache.get("city", "")
        except Exception as exc:
            log.warning("Geo lookup failed: %s", exc)
            self._geo_cache = self._cache.get("city", "")

        return self._geo_cache

    def get_icon(self, icon_code: str, size: tuple, badge: bool,
                 bg_hex: str) -> object:
        """Download and cache OWM icon. Adds dark badge if badge=True."""
        if not PIL_AVAILABLE:
            return None
        key = f"{icon_code}_{size[0]}_{badge}"
        if key in self._icon_cache:
            return self._icon_cache[key]
        try:
            url  = OWM_ICON_URL.format(icon_code)
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img  = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            img  = img.resize(size, Image.LANCZOS)

            # Parse background colour
            bg_r = int(bg_hex[1:3], 16)
            bg_g = int(bg_hex[3:5], 16)
            bg_b = int(bg_hex[5:7], 16)

            if badge:
                # Draw dark rounded rectangle behind icon
                pad    = 6
                canvas = Image.new("RGBA",
                    (size[0] + pad*2, size[1] + pad*2), (bg_r, bg_g, bg_b, 255))
                draw   = ImageDraw.Draw(canvas)
                draw.rounded_rectangle(
                    [2, 2, canvas.width-2, canvas.height-2],
                    radius=12, fill=(30, 30, 30, 220))
                canvas.paste(img, (pad, pad), mask=img.split()[3])
                final = canvas
            else:
                final = Image.new("RGBA", size, (bg_r, bg_g, bg_b, 255))
                final.paste(img, mask=img.split()[3])

            tk_img = ImageTk.PhotoImage(final.convert("RGB"))
            self._icon_cache[key] = tk_img
            log.info("Icon cached: %s", icon_code)
            return tk_img
        except Exception as exc:
            log.warning("Icon fetch failed (%s): %s", icon_code, exc)
            return None

    def _parse(self, d: dict) -> dict:
        weather    = d.get("weather", [{}])[0]
        main       = d.get("main",    {})
        wind       = d.get("wind",    {})
        icon_code  = weather.get("icon", "01d")
        unit_sym   = "°C" if self.units == "metric" else "°F"
        speed_unit = "km/h" if self.units == "metric" else "mph"
        wind_speed = wind.get("speed", 0)
        if self.units == "metric":
            wind_speed = wind_speed * 3.6
        return {
            "description": weather.get("description", "").capitalize(),
            "icon_code":   icon_code,
            "temp":        f"{main.get('temp',       0):.1f}{unit_sym}",
            "feels_like":  f"{main.get('feels_like', 0):.1f}{unit_sym}",
            "humidity":    f"{main.get('humidity',   0)}%",
            "temp_min":    f"{main.get('temp_min',   0):.1f}{unit_sym}",
            "temp_max":    f"{main.get('temp_max',   0):.1f}{unit_sym}",
            "wind":        f"{wind_speed:.0f} {speed_unit} "
                           f"{deg_to_compass(wind.get('deg', 0))}",
            "city":        d.get("name", ""),
            "lat":         d.get("coord", {}).get("lat"),
            "lon":         d.get("coord", {}).get("lon"),
        }

    @staticmethod
    def _placeholder() -> dict:
        return {
            "description": "Unavailable",
            "icon_code":   "01d",
            "temp":        "--",
            "feels_like":  "--",
            "humidity":    "--",
            "temp_min":    "--",
            "temp_max":    "--",
            "wind":        "--",
            "city":        "",
        }


# ── GUI ───────────────────────────────────────────────────────────────────────
class ClockApp:
    def __init__(self, root: tk.Tk, cfg: configparser.RawConfigParser):
        self.root = root
        display   = cfg["display"]
        owm       = cfg["openweathermap"]

        # Theme
        theme_name = cfg.get("colours", "theme", fallback="dark_blue")
        self.theme = THEMES.get(theme_name, THEMES["dark_blue"])

        self.width    = display.getint("width",  fallback=480)
        self.height   = display.getint("height", fallback=320)
        self.time_fmt = display.get("time_format", fallback="%H:%M:%S")
        self.date_fmt = display.get("date_format", fallback="%A  %d %B %Y")

        self.weather = WeatherFetcher(
            api_key  = owm.get("api_key",  ""),
            location = owm.get("location", "q=London,uk"),
            units    = owm.get("units",    "metric"),
        )

        self._current_icon_code = None
        self._icon_image        = None
        self._local_ip          = get_local_ip()

        self._setup_window()
        self._build_ui()
        self._tick()

    def _setup_window(self):
        self.root.title("RPi Clock")
        self.root.configure(bg=self.theme["bg"])
        self.root.overrideredirect(True)
        self.root.geometry(f"{self.width}x{self.height}+0+0")
        self.root.resizable(False, False)
        self.root.config(cursor="none")
        self.root.bind("<Escape>", lambda _e: self.root.destroy())

    def _build_ui(self):
        W = self.width
        H = self.height
        T = self.theme

        # ── left panel ───────────────────────────────────────────────────────
        left_w = int(W * 0.62)
        left   = tk.Frame(self.root, bg=T["bg"], width=left_w, height=H)
        left.place(x=0, y=0)
        left.pack_propagate(False)

        self.lbl_time = tk.Label(
            left, text="00:00:00", bg=T["bg"], fg=T["time"],
            font=("FreeMono", 44, "bold"))
        self.lbl_time.place(relx=0.5, rely=0.25, anchor="center")

        self.lbl_date = tk.Label(
            left, text="", bg=T["bg"], fg=T["date"],
            font=("DejaVu Sans", 14))
        self.lbl_date.place(relx=0.5, rely=0.52, anchor="center")

        self.lbl_city = tk.Label(
            left, text="", bg=T["bg"], fg=T["city"],
            font=("DejaVu Sans", 14))
        self.lbl_city.place(relx=0.5, rely=0.70, anchor="center")

        self.lbl_ip = tk.Label(
            left, text=self._local_ip, bg=T["bg"], fg=T["ip"],
            font=("DejaVu Sans", 12))
        self.lbl_ip.place(relx=0.5, rely=0.84, anchor="center")

        # ── divider ──────────────────────────────────────────────────────────
        tk.Frame(self.root, bg=T["divider"], width=2,
                 height=int(H * 0.88)).place(
            x=int(W * 0.625), y=int(H * 0.06))

        # ── right panel ──────────────────────────────────────────────────────
        rx  = int(W * 0.64)
        rw  = W - rx
        right = tk.Frame(self.root, bg=T["bg"], width=rw, height=H)
        right.place(x=rx, y=0)
        right.pack_propagate(False)

        self.lbl_icon = tk.Label(right, bg=T["bg"])
        self.lbl_icon.place(relx=0.5, rely=0.16, anchor="center")

        self.lbl_temp = tk.Label(
            right, text="--", bg=T["bg"], fg=T["temp"],
            font=("DejaVu Sans", 24, "bold"))
        self.lbl_temp.place(relx=0.5, rely=0.40, anchor="center")

        self.lbl_desc = tk.Label(
            right, text="", bg=T["bg"], fg=T["desc"],
            font=("DejaVu Sans", 12), wraplength=int(rw * 0.92),
            justify="center")
        self.lbl_desc.place(relx=0.5, rely=0.55, anchor="center")

        self.lbl_detail = tk.Label(
            right, text="", bg=T["bg"], fg=T["detail"],
            font=("DejaVu Sans", 10), justify="left")
        self.lbl_detail.place(relx=0.5, rely=0.73, anchor="center")

        self.lbl_minmax = tk.Label(
            right, text="", bg=T["bg"], fg=T["minmax"],
            font=("DejaVu Sans", 10), justify="center")
        self.lbl_minmax.place(relx=0.5, rely=0.91, anchor="center")

    def _update_icon(self, icon_code: str):
        if icon_code == self._current_icon_code:
            return
        self._current_icon_code = icon_code
        img = self.weather.get_icon(
            icon_code,
            size=(80, 80),
            badge=self.theme["icon_badge"],
            bg_hex=self.theme["bg"],
        )
        if img:
            self._icon_image = img
            self.lbl_icon.config(image=img, text="")
        else:
            self.lbl_icon.config(image="", text=f"[{icon_code}]",
                                 font=("DejaVu Sans", 11),
                                 fg=self.theme["desc"])

    def _tick(self):
        now = datetime.now()
        self.lbl_time.config(text=now.strftime(self.time_fmt))
        self.lbl_date.config(text=now.strftime(self.date_fmt))

        w = self.weather.get()
        self._update_icon(w["icon_code"])
        self.lbl_temp.config(text=w["temp"])
        self.lbl_desc.config(text=w["description"])
        self.lbl_detail.config(
            text=f"Feels Like: {w['feels_like']}\n"
                 f"Humidity:   {w['humidity']}\n"
                 f"Wind:       {w['wind']}")
        self.lbl_minmax.config(
            text=f"↓ {w['temp_min']}   ↑ {w['temp_max']}")

        # Location string (cached — only hits geo API once per hour)
        loc = self.weather.get_location_string()
        self.lbl_city.config(text=loc)

        self.root.after(1000, self._tick)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).parent / "rpi_clock.cfg")
    cfg  = load_config(cfg_path)
    root = tk.Tk()
    ClockApp(root, cfg)
    root.mainloop()


if __name__ == "__main__":
    main()
