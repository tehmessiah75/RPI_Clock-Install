#!/usr/bin/env python3
"""
rpi_clock.py  —  Waveshare 3.5" LCD (A) clock + weather display
Standalone replacement for the archived texadactyl/rpi_clock project.

Dependencies: tkinter (stdlib), requests (python3-requests), Pillow (python3-pil.imagetk)
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
from pathlib import Path
from datetime import datetime

# PIL for OWM icon display
try:
    from PIL import Image, ImageTk
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


# ── Config ────────────────────────────────────────────────────────────────────
def load_config(cfg_path: str) -> configparser.RawConfigParser:
    cfg = configparser.RawConfigParser()   # RawConfigParser: % is not special
    if not os.path.isfile(cfg_path):
        log.error("Config file not found: %s", cfg_path)
        sys.exit(1)
    cfg.read(cfg_path)
    return cfg


# ── OpenWeatherMap ────────────────────────────────────────────────────────────
OWM_URL      = "https://api.openweathermap.org/data/2.5/weather"
OWM_ICON_URL = "https://openweathermap.org/img/wn/{}@2x.png"

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
        self.location = location        # e.g. "q=Adelaide,au" or "zip=75248,us"
        self.units    = units           # "metric" or "imperial"
        self._cache:      dict  = {}
        self._icon_cache: dict  = {}    # icon_code -> PIL ImageTk
        self._last_fetch: float = 0.0
        self.fetch_interval: int = 600  # seconds between API calls

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

    def get_icon(self, icon_code: str, size: tuple = (80, 80)):
        """Download and cache OWM icon as a PIL ImageTk. Returns None on failure."""
        if not PIL_AVAILABLE:
            return None
        key = f"{icon_code}_{size[0]}"
        if key in self._icon_cache:
            return self._icon_cache[key]
        try:
            url  = OWM_ICON_URL.format(icon_code)
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img  = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            img  = img.resize(size, Image.LANCZOS)
            # Composite onto the background colour to remove transparency
            bg   = Image.new("RGBA", size, (10, 10, 26, 255))   # matches BG #0a0a1a
            bg.paste(img, mask=img.split()[3])
            tk_img = ImageTk.PhotoImage(bg.convert("RGB"))
            self._icon_cache[key] = tk_img
            log.info("Icon downloaded: %s", icon_code)
            return tk_img
        except Exception as exc:
            log.warning("Icon fetch failed (%s): %s", icon_code, exc)
            return None

    def _parse(self, d: dict) -> dict:
        weather   = d.get("weather", [{}])[0]
        main      = d.get("main",    {})
        wind      = d.get("wind",    {})
        icon_code = weather.get("icon", "01d")
        unit_sym  = "°C" if self.units == "metric" else "°F"
        speed_unit = "km/h" if self.units == "metric" else "mph"
        wind_speed = wind.get("speed", 0)
        if self.units == "metric":
            wind_speed = wind_speed * 3.6   # m/s → km/h
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
    # Colour palette
    BG        = "#0a0a1a"
    FG_TIME   = "#ffffff"
    FG_DATE   = "#aaddff"
    FG_CITY   = "#88ccff"
    FG_TEMP   = "#ffdd88"
    FG_DESC   = "#dddddd"
    FG_DETAIL = "#bbbbbb"
    FG_MINMAX = "#aaaaaa"
    DIVIDER   = "#223355"

    def __init__(self, root: tk.Tk, cfg: configparser.RawConfigParser):
        self.root = root
        display   = cfg["display"]
        owm       = cfg["openweathermap"]

        self.width    = display.getint("width",  fallback=480)
        self.height   = display.getint("height", fallback=320)
        self.time_fmt = display.get("time_format", fallback="%H:%M:%S")
        self.date_fmt = display.get("date_format", fallback="%A  %d %B %Y")

        self.weather = WeatherFetcher(
            api_key  = owm.get("api_key",   ""),
            location = owm.get("location",  "q=London,uk"),
            units    = owm.get("units",     "metric"),
        )

        self._current_icon_code = None   # track icon changes
        self._icon_image        = None   # hold reference to prevent GC

        self._setup_window()
        self._build_ui()
        self._tick()

    # ── window setup — correct method for framebuffer fullscreen ──
    def _setup_window(self):
        self.root.title("RPi Clock")
        self.root.configure(bg=self.BG)

        # overrideredirect removes the window border/titlebar entirely,
        # then we force exact geometry — this is the reliable method on
        # framebuffer displays where -fullscreen can misbehave.
        self.root.overrideredirect(True)
        self.root.geometry(f"{self.width}x{self.height}+0+0")

        self.root.resizable(False, False)
        self.root.config(cursor="none")

        # Ctrl+C in terminal still works; touch-hold could be wired here later
        self.root.bind("<Escape>", lambda _e: self.root.destroy())

    # ── UI layout ──
    def _build_ui(self):
        W = self.width
        H = self.height

        # ── left panel: clock + date + city ──────────────────────────────────
        left = tk.Frame(self.root, bg=self.BG, width=int(W * 0.54), height=H)
        left.place(x=0, y=0)
        left.pack_propagate(False)

        self.lbl_time = tk.Label(
            left, text="00:00:00", bg=self.BG, fg=self.FG_TIME,
            font=("FreeMono", 48, "bold"))
        self.lbl_time.place(relx=0.5, rely=0.28, anchor="center")

        self.lbl_date = tk.Label(
            left, text="", bg=self.BG, fg=self.FG_DATE,
            font=("DejaVu Sans", 13))
        self.lbl_date.place(relx=0.5, rely=0.54, anchor="center")

        self.lbl_city = tk.Label(
            left, text="", bg=self.BG, fg=self.FG_CITY,
            font=("DejaVu Sans", 12))
        self.lbl_city.place(relx=0.5, rely=0.72, anchor="center")

        # ── vertical divider ─────────────────────────────────────────────────
        tk.Frame(self.root, bg=self.DIVIDER, width=2, height=int(H * 0.88)).place(
            x=int(W * 0.545), y=int(H * 0.06))

        # ── right panel: weather ──────────────────────────────────────────────
        rx = int(W * 0.56)
        rw = W - rx
        right = tk.Frame(self.root, bg=self.BG, width=rw, height=H)
        right.place(x=rx, y=0)
        right.pack_propagate(False)

        # Icon — either OWM image or fallback text
        self.lbl_icon = tk.Label(
            right, bg=self.BG, fg=self.FG_TIME,
            font=("DejaVu Sans", 11))
        self.lbl_icon.place(relx=0.5, rely=0.16, anchor="center")

        self.lbl_temp = tk.Label(
            right, text="--", bg=self.BG, fg=self.FG_TEMP,
            font=("DejaVu Sans", 26, "bold"))
        self.lbl_temp.place(relx=0.5, rely=0.40, anchor="center")

        self.lbl_desc = tk.Label(
            right, text="", bg=self.BG, fg=self.FG_DESC,
            font=("DejaVu Sans", 13), wraplength=int(rw * 0.92), justify="center")
        self.lbl_desc.place(relx=0.5, rely=0.57, anchor="center")

        self.lbl_detail = tk.Label(
            right, text="", bg=self.BG, fg=self.FG_DETAIL,
            font=("DejaVu Sans", 11), justify="center")
        self.lbl_detail.place(relx=0.5, rely=0.74, anchor="center")

        self.lbl_minmax = tk.Label(
            right, text="", bg=self.BG, fg=self.FG_MINMAX,
            font=("DejaVu Sans", 11), justify="center")
        self.lbl_minmax.place(relx=0.5, rely=0.90, anchor="center")

    # ── update icon ──────────────────────────────────────────────────────────
    def _update_icon(self, icon_code: str):
        if icon_code == self._current_icon_code:
            return   # no change needed
        self._current_icon_code = icon_code

        img = self.weather.get_icon(icon_code, size=(80, 80))
        if img:
            self._icon_image = img           # keep reference — prevents GC
            self.lbl_icon.config(image=img, text="")
        else:
            # Fallback: show icon code as text if PIL unavailable or fetch failed
            self.lbl_icon.config(image="", text=f"[{icon_code}]",
                                 font=("DejaVu Sans", 12))

    # ── tick every second ─────────────────────────────────────────────────────
    def _tick(self):
        now = datetime.now()
        self.lbl_time.config(text=now.strftime(self.time_fmt))
        self.lbl_date.config(text=now.strftime(self.date_fmt))

        w = self.weather.get()
        self._update_icon(w["icon_code"])
        self.lbl_city.config(text=w["city"])
        self.lbl_temp.config(text=w["temp"])
        self.lbl_desc.config(text=w["description"])
        self.lbl_detail.config(
            text=f"Feels {w['feels_like']}   Hum {w['humidity']}\n"
                 f"Wind {w['wind']}")
        self.lbl_minmax.config(
            text=f"↓ {w['temp_min']}   ↑ {w['temp_max']}")

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
