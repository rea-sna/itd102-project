# QUT Kelvin Grove bus stop IDs (by platform)
PLATFORM_1_STOP_IDS = {"884"}   # Platform 1 — outbound
PLATFORM_2_STOP_IDS = {"889"}   # Platform 2 — inbound

PLATFORM_1_LABEL = "Platform 1 - Roma Street, City, Woolloongabba, UQ Lakes"
PLATFORM_2_LABEL = "Platform 2 - RBWH, Carseldine, Chermside, Bracken Ridge"

# Backward compatibility for app.py
STOP_IDS = PLATFORM_1_STOP_IDS | PLATFORM_2_STOP_IDS

# Max departures shown per platform (native.py)
MAX_PER_PLATFORM = 8
# For app.py
MAX_DEPARTURES = 12

# Cache TTL in seconds — tuned for RPi 3 load
CACHE_TTL = 30

# Flask server settings
HOST = "0.0.0.0"
PORT = 40053

# Display name
LOCATION_NAME = "QUT Kelvin Grove"

# Volume settings (0.0 – 1.0)
CHIME_VOLUME    = 0.6   # chime volume
ANNOUNCE_VOLUME = 1.0   # announcement volume
