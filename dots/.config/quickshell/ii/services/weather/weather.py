#!/usr/bin/env python3
import openmeteo_requests
import requests_cache
from retry_requests import retry
import json
import sys
from datetime import datetime
from geopy.geocoders import Nominatim

# ---------------------------------------------------------------------------
# Resolve coordinates from arguments:
#   weather.py <lat> <lon>     — GPS coordinates
#   weather.py <city name>     — geocode the city name
#   weather.py                 — fall back to hardcoded default
# ---------------------------------------------------------------------------
DEFAULT_LAT = 43.8668
DEFAULT_LON = -79.2663

latitude = DEFAULT_LAT
longitude = DEFAULT_LON

if len(sys.argv) >= 3:
    # Two numeric args → lat/lon from GPS
    try:
        latitude = float(sys.argv[1])
        longitude = float(sys.argv[2])
    except ValueError:
        pass  # keep defaults
elif len(sys.argv) == 2:
    # One arg → city name; geocode it
    try:
        geolocator = Nominatim(user_agent="quickshell_weather")
        geo = geolocator.geocode(sys.argv[1])
        if geo:
            latitude = geo.latitude
            longitude = geo.longitude
    except Exception:
        pass  # keep defaults

# ---------------------------------------------------------------------------
# Open-Meteo client setup
# ---------------------------------------------------------------------------
cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

# ---------------------------------------------------------------------------
# WMO weather code → wttr.in code mapping
# ---------------------------------------------------------------------------
def wmo_to_wttr_code(wmo_code, is_day):
    mapping = {
        0: "113", 1: "116", 2: "119", 3: "122",
        45: "143", 48: "248",
        51: "263", 53: "266", 55: "296",
        56: "281", 57: "284",
        61: "293", 63: "296", 65: "302",
        66: "311", 67: "314",
        71: "323", 73: "326", 75: "338", 77: "335",
        80: "353", 81: "356", 82: "359",
        85: "368", 86: "371",
        95: "386", 96: "392", 99: "395",
    }
    return mapping.get(wmo_code, "113")

# ---------------------------------------------------------------------------
# Wind direction helper
# ---------------------------------------------------------------------------
def get_wind_direction(degrees):
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return directions[round(degrees / 22.5) % 16]

# ---------------------------------------------------------------------------
# API request
# ---------------------------------------------------------------------------
url = "https://api.open-meteo.com/v1/forecast"
params = {
    "latitude": latitude,
    "longitude": longitude,
    "daily": ["uv_index_max", "sunrise", "sunset"],
    "hourly": ["surface_pressure", "visibility"],
    "current": [
        "temperature_2m",       # 0
        "relative_humidity_2m", # 1
        "is_day",               # 2
        "precipitation",        # 3
        "surface_pressure",     # 4
        "wind_speed_10m",       # 5
        "wind_direction_10m",   # 6
        "apparent_temperature", # 7
        "rain",                 # 8
        "snowfall",             # 9
        "weather_code",         # 10
    ],
    "timezone": "auto",
    "wind_speed_unit": "kmh",
}

try:
    responses = openmeteo.weather_api(url, params=params)
    response = responses[0]

    # Reverse-geocode to get a human-readable city name
    try:
        geolocator = Nominatim(user_agent="quickshell_weather")
        loc = geolocator.reverse(f"{latitude}, {longitude}", language="en")
        if loc and loc.raw.get('address'):
            addr = loc.raw['address']
            city_name = (addr.get('city') or addr.get('town') or
                         addr.get('village') or addr.get('municipality') or
                         addr.get('county') or 'Unknown')
        else:
            city_name = f"{latitude:.2f}°N, {longitude:.2f}°E"
    except Exception:
        city_name = f"{latitude:.2f}°N, {longitude:.2f}°E"

    # Current variables
    current = response.Current()
    temp_c      = current.Variables(0).Value()
    humidity    = int(current.Variables(1).Value())
    is_day      = current.Variables(2).Value() == 1
    precip_mm   = current.Variables(3).Value()
    pressure_hpa = current.Variables(4).Value()
    wind_kmph   = current.Variables(5).Value()
    wind_deg    = current.Variables(6).Value()
    feels_c     = current.Variables(7).Value()
    wmo_code    = int(current.Variables(10).Value())

    # Hourly visibility (first index ≈ current hour)
    hourly = response.Hourly()
    hourly_visibility = hourly.Variables(1).ValuesAsNumpy()
    visibility_km = round(float(hourly_visibility[0]) / 1000, 1) if len(hourly_visibility) > 0 else 10.0

    # Daily UV / sunrise / sunset
    daily = response.Daily()
    uv_max     = float(daily.Variables(0).ValuesAsNumpy()[0])
    sunrise_ts = int(daily.Variables(1).ValuesInt64AsNumpy()[0])
    sunset_ts  = int(daily.Variables(2).ValuesInt64AsNumpy()[0])
    sunrise_str = datetime.fromtimestamp(sunrise_ts).strftime("%I:%M %p")
    sunset_str  = datetime.fromtimestamp(sunset_ts).strftime("%I:%M %p")

    # Imperial unit conversions
    temp_f       = round(temp_c * 9 / 5 + 32)
    feels_f      = round(feels_c * 9 / 5 + 32)
    wind_mph     = round(wind_kmph * 0.621371)
    precip_in    = round(precip_mm * 0.0393701, 2)
    visibility_mi = round(visibility_km * 0.621371, 1)
    pressure_psi  = round(pressure_hpa * 0.02953, 2)

    output = {
        "current": {
            # Metric
            "temp_C":         int(round(temp_c)),
            "FeelsLikeC":     int(round(feels_c)),
            "windspeedKmph":  int(round(wind_kmph)),
            "precipMM":       round(precip_mm, 1),
            "visibility":     int(round(visibility_km)),
            "pressure":       int(round(pressure_hpa)),
            # Imperial
            "temp_F":         int(temp_f),
            "FeelsLikeF":     int(feels_f),
            "windspeedMiles": int(wind_mph),
            "precipInches":   precip_in,
            "visibilityMiles": visibility_mi,
            "pressureInches": pressure_psi,
            # Shared
            "humidity":          humidity,
            "winddir16Point":    get_wind_direction(wind_deg),
            "uvIndex":           int(round(uv_max)),
            "weatherCode":       wmo_to_wttr_code(wmo_code, is_day),
        },
        "location": {
            "areaName": [{"value": city_name}]
        },
        "astronomy": {
            "sunrise": sunrise_str,
            "sunset":  sunset_str,
        }
    }

    print(json.dumps(output))

except Exception as e:
    error_output = {
        "error": str(e),
        "current": {},
        "location": {"areaName": [{"value": "Error"}]},
        "astronomy": {"sunrise": "00:00", "sunset": "00:00"}
    }
    print(json.dumps(error_output), file=sys.stderr)
    sys.exit(1)

