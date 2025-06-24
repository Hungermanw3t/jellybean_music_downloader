import os
from dotenv import load_dotenv
load_dotenv()

# Qobuz API Configuration
BASE_URL = "https://eu.qobuz.squid.wtf"
QOBUZ_API_BASE_URLS = [
    "https://eu.qobuz.squid.wtf",
    "https://us.qobuz.squid.wtf"
]
CURRENT_QOBUZ_API_INDEX = 0

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json"
}

QOBUZ_CDN_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Origin": "https://play.qobuz.com",
    "Referer": "https://play.qobuz.com/"
}

# Download Directory
DOWNLOAD_BASE_DIR = os.getenv("DOWNLOAD_BASE_DIR", "downloads")

# Quality Map
QUALITY_MAP = {
    "FLAC": 27,
    "MP3": 5,
}

# MusicBrainz Configuration
MUSICBRAINZ_USER_AGENT = os.getenv(
    "MUSICBRAINZ_USER_AGENT",
    "QobuzSquidDownloader/1.0 ( your.email@example.com )"
)

# AcoustID Configuration
ACOUSTID_API_KEY = os.getenv("ACOUSTID_API_KEY", "YOUR_ACOUSTID_API_KEY_HERE")
FPCALC_EXECUTABLE_PATH = "/usr/local/bin/fpcalc"

# Runtime caches
SESSION_COOKIES = {}
_album_release_cache = {}

# Format mapping
TRANSCODE_MAP = {
    "FLAC": {"download": "FLAC", "ext": "flac"},
    "MP3":  {"download": "MP3",  "ext": "mp3"},
    "ALAC": {"download": "FLAC", "ext": "m4a"},
}

# Logging
LOGGING_ENABLED = os.getenv("LOGGING_ENABLED", "false").lower() == "true"

def switch_qobuz_api_url():
    global CURRENT_QOBUZ_API_INDEX, BASE_URL
    CURRENT_QOBUZ_API_INDEX = (CURRENT_QOBUZ_API_INDEX + 1) % len(QOBUZ_API_BASE_URLS)
    BASE_URL = QOBUZ_API_BASE_URLS[CURRENT_QOBUZ_API_INDEX]