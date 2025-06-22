import os
from dotenv import load_dotenv
load_dotenv()

# Qobuz API Configuration
BASE_URL = os.getenv("QOBUZ_API_BASE_URL", "https://api.squid.wtf")
API_HEADERS = {
    "User-Agent": os.getenv("QOBUZ_API_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json"
}

# Qobuz CDN Download Headers
QOBUZ_CDN_DOWNLOAD_HEADERS = {
    "User-Agent": os.getenv("QOBUZ_CDN_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "*/*",
    "Origin": "https://play.qobuz.com",
    "Referer": "https://play.qobuz.com/"
}

# Download Directory
DOWNLOAD_BASE_DIR = os.getenv("DOWNLOAD_BASE_DIR", "downloads")

# Qobuz Quality Map (assuming values required by squid.wtf API)
QUALITY_MAP = {
    "FLAC": 27,        # Highest quality FLAC
    "MP3": 5,          # MP3 320kbps
}

# MusicBrainz Configuration
MUSICBRAINZ_USER_AGENT = os.getenv(
    "MUSICBRAINZ_USER_AGENT",
    "QobuzSquidDownloader/1.0 ( your.email@example.com )"
)

# AcoustID Configuration
ACOUSTID_API_KEY = os.getenv("ACOUSTID_API_KEY", "YOUR_ACOUSTID_API_KEY_HERE")

# FPCALC_EXECUTABLE_PATH is assumed to be in the same directory as the script, or discoverable
_script_dir = os.path.dirname(os.path.abspath(__file__))
_fpcalc_name = "fpcalc.exe" if os.name == "nt" else "fpcalc" # 'nt' for Windows
FPCALC_EXECUTABLE_PATH = os.getenv("FPCALC_EXECUTABLE_PATH", "/usr/local/bin/fpcalc")


# Session cookies for Qobuz API (managed during runtime)
SESSION_COOKIES = {}

# Cache for chosen MusicBrainz Release ID per Qobuz Album ID
_album_release_cache = {}

# Map of requested output format to (download_format, output_extension, transcoder_function)
TRANSCODE_MAP = {
    "FLAC": {"download": "FLAC", "ext": "flac"},
    "MP3":  {"download": "MP3",  "ext": "mp3"},
    "ALAC": {"download": "FLAC", "ext": "m4a"},
    "AAC":  {"download": "FLAC", "ext": "m4a"},
    # Add more as needed
}

# Logging flag
LOGGING_ENABLED = os.getenv("LOGGING_ENABLED", "false").lower() == "true"

QOBUZ_API_BASE_URLS = [
    os.getenv("QOBUZ_API_BASE_URL", "https://eu.qobuz.squid.wtf"),
    os.getenv("QOBUZ_API_BASE_URL_2", "https://us.qobuz.squid.wtf")
]
CURRENT_QOBUZ_API_INDEX = 0
BASE_URL = QOBUZ_API_BASE_URLS[CURRENT_QOBUZ_API_INDEX]

def switch_qobuz_api_url():
    global CURRENT_QOBUZ_API_INDEX, BASE_URL
    CURRENT_QOBUZ_API_INDEX = (CURRENT_QOBUZ_API_INDEX + 1) % len(QOBUZ_API_BASE_URLS)
    BASE_URL = QOBUZ_API_BASE_URLS[CURRENT_QOBUZ_API_INDEX]