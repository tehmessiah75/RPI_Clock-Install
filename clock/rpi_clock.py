#!/usr/bin/env python3
"""
rpi_clock.py  —  Waveshare 3.5" LCD (A) clock + weather display
Standalone replacement for the archived texadactyl/rpi_clock project.

Dependencies: tkinter (stdlib), requests (python3-requests)
Config file:  rpi_clock.cfg  (same directory)
"""

import tkinter as tk
import requests
import configparser
import time
import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("rpi_clock")


# ── Config ────────────────────────────────────────────────────────────────────
def load_config(cfg_path: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if not os.path.isfile(cfg_path):
        log.error("Config file not found: %s", cfg_path)
        sys.exit(1)
    cfg.read(cfg_path)
    return cfg


# ── OpenWeatherMap ────────────────────────────────────────────────────────────
OWM_URL = "https://api.openweathermap.org/data/2.5/weather"

WEATHER_ICONS = {
    # Clear
    "01d": "☀",  "01n": "🌙",
    # Few clouds
    "02d": "🌤",  "02n": "🌤",
    # Scattered clouds
    "03d": "⛅",  "03n": "⛅",
    # Broken clouds
    "04d": "☁",  "04n": "☁",
    # Shower rain
    "09d": "🌧",  "09n": "🌧",
    # Rain
    "10d": "🌦",  "10n": "🌦",
    # Thunderstorm
    "11d": "⛈",  "11n": "⛈",
    # Snow
    "13d": "❄",  "13n": "❄",
    # Mist/fog
    "50d": "🌫",  "50n": "🌫",
}

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
        self.api_key = api_key
        self.location = location        # e.g. "q=Adelaide,au" or "zip=75248,us"
        self.units = units              # "metric" or "imperial"
        self._cache: dict = {}
        self._last_fetch: float = 0.0
        self.fetch_interval: int = 600  # seconds between API calls

    def get(self) -> dict:
        now = time.time()
        if now - self._last_fetch < self.fetch_interval and self._cache:
            return self._cache

        params = {"appid": self.api_key, "units": self.units}
        # location string is like "q=Adelaide,au" — split key=value
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

    def _parse(self, d: dict) -> dict:
        weather = d.get("weather", [{}])[0]
        main = d.get("main", {})
        wind = d.get("wind", {})
        icon_code = weather.get("icon", "01d")
        unit_sym = "°C" if self.units == "metric" else "°F"
        speed_unit = "km/h" if self.units == "metric" else "mph"
        wind_speed = wind.get("speed", 0)
        if self.units == "metric":
            wind_speed = wind_speed * 3.6  # m/s → km/h
        return {
            "description": weather.get("description", "").capitalize(),
            "icon": WEATHER_ICONS.get(icon_code, "?"),
            "temp": f"{main.get('temp', 0):.1f}{unit_sym}",
            "feels_like": f"{main.get('feels_like', 0):.1f}{unit_sym}",
            "humidity": f"{main.get('humidity', 0)}%",
            "temp_min": f"{main.get('temp_min', 0):.1f}{unit_sym}",
            "temp_max": f"{main.get('temp_max', 0):.1f}{unit_sym}",
            "wind": f"{wind_speed:.0f} {speed_unit} {deg_to_compass(wind.get('deg', 0))}",
            "city": d.get("name", ""),
        }

    @staticmethod
    def _placeholder() -> dict:
        return {
            "description": "Unavailable",
            "icon": "?",
            "temp": "--",
            "feels_like": "--",
            "humidity": "--",
            "temp_min": "--",
            "temp_max": "--",
            "wind": "--",
            "city": "",
        }


# ── GUI ───────────────────────────────────────────────────────────────────────
class ClockApp:
    # Colour palette
    BG       = "#0a0a1a"
    FG_TIME  = "#ffffff"
    FG_DATE  = "#aaddff"
    FG_CITY  = "#88ccff"
    FG_TEMP  = "#ffdd88"
    FG_DESC  = "#cccccc"
    FG_DETAIL= "#999999"
    FG_ICON  = "#ffffff"

    def __init__(self, root: tk.Tk, cfg: configparser.ConfigParser):
        self.root = root
        display = cfg["display"]
        owm     = cfg["openweathermap"]

        self.fullscreen   = display.getboolean("fullscreen", fallback=True)
        self.width        = display.getint("width",  fallback=480)
        self.height       = display.getint("height", fallback=320)
        self.time_fmt     = display.get("time_format", fallback="%H:%M:%S")
        self.date_fmt     = display.get("date_format", fallback="%A  %d %B %Y")
        self.show_seconds = display.getboolean("show_seconds", fallback=True)

        self.weather = WeatherFetcher(
            api_key  = owm.get("api_key", ""),
            location = owm.get("location", "q=London,uk"),
            units    = owm.get("units", "metric"),
        )

        self._setup_window()
        self._build_ui()
        self._tick()

    # ── window setup ──
    def _setup_window(self):
        self.root.title("RPi Clock")
        self.root.configure(bg=self.BG)
        if self.fullscreen:
            self.root.attributes("-fullscreen", True)
        else:
            self.root.geometry(f"{self.width}x{self.height}")
        self.root.resizable(False, False)
        # Hide cursor on the display
        self.root.config(cursor="none")
        # Allow ESC to exit (useful during setup/debug)
        self.root.bind("<Escape>", lambda _e: self.root.destroy())
        self.root.bind("<F11>", lambda _e: self.root.attributes(
            "-fullscreen", not self.root.attributes("-fullscreen")))

    # ── UI layout ──
    def _build_ui(self):
        root = self.root

        # ---- left column: clock + date ----
        left = tk.Frame(root, bg=self.BG)
        left.place(relx=0.0, rely=0.0, relwidth=0.55, relheight=1.0)

        self.lbl_time = tk.Label(
            left, text="00:00:00", bg=self.BG, fg=self.FG_TIME,
            font=("DejaVu Sans Mono", 52, "bold"), anchor="center")
        self.lbl_time.place(relx=0.5, rely=0.3, anchor="center")

        self.lbl_date = tk.Label(
            left, text="", bg=self.BG, fg=self.FG_DATE,
            font=("DejaVu Sans", 14), anchor="center")
        self.lbl_date.place(relx=0.5, rely=0.55, anchor="center")

        self.lbl_city = tk.Label(
            left, text="", bg=self.BG, fg=self.FG_CITY,
            font=("DejaVu Sans", 12), anchor="center")
        self.lbl_city.place(relx=0.5, rely=0.70, anchor="center")

        # divider
        tk.Frame(root, bg="#223355", width=2).place(
            relx=0.55, rely=0.05, relheight=0.90)

        # ---- right column: weather ----
        right = tk.Frame(root, bg=self.BG)
        right.place(relx=0.57, rely=0.0, relwidth=0.43, relheight=1.0)

        self.lbl_icon = tk.Label(
            right, text="?", bg=self.BG, fg=self.FG_ICON,
            font=("DejaVu Sans", 42))
        self.lbl_icon.place(relx=0.5, rely=0.18, anchor="center")

        self.lbl_temp = tk.Label(
            right, text="--", bg=self.BG, fg=self.FG_TEMP,
            font=("DejaVu Sans", 26, "bold"))
        self.lbl_temp.place(relx=0.5, rely=0.40, anchor="center")

        self.lbl_desc = tk.Label(
            right, text="", bg=self.BG, fg=self.FG_DESC,
            font=("DejaVu Sans", 11), wraplength=180, justify="center")
        self.lbl_desc.place(relx=0.5, rely=0.56, anchor="center")

        self.lbl_detail = tk.Label(
            right, text="", bg=self.BG, fg=self.FG_DETAIL,
            font=("DejaVu Sans", 9), justify="center")
        self.lbl_detail.place(relx=0.5, rely=0.76, anchor="center")

        self.lbl_minmax = tk.Label(
            right, text="", bg=self.BG, fg=self.FG_DETAIL,
            font=("DejaVu Sans", 9), justify="center")
        self.lbl_minmax.place(relx=0.5, rely=0.90, anchor="center")

    # ── tick every second ──
    def _tick(self):
        now = datetime.now()
        self.lbl_time.config(text=now.strftime(self.time_fmt))
        self.lbl_date.config(text=now.strftime(self.date_fmt))

        # refresh weather (cached internally — only hits API every 10 min)
        w = self.weather.get()
        self.lbl_city.config(text=w["city"])
        self.lbl_icon.config(text=w["icon"])
        self.lbl_temp.config(text=w["temp"])
        self.lbl_desc.config(text=w["description"])
        self.lbl_detail.config(
            text=f"Feels {w['feels_like']}   Hum {w['humidity']}\nWind {w['wind']}")
        self.lbl_minmax.config(
            text=f"↓ {w['temp_min']}  ↑ {w['temp_max']}")

        self.root.after(1000, self._tick)


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).parent / "rpi_clock.cfg")

    cfg = load_config(cfg_path)

    root = tk.Tk()
    ClockApp(root, cfg)
    root.mainloop()


if __name__ == "__main__":
    main()
