import re
import os
from config import LOGGING_ENABLED

def clean_filename(filename):
    """Cleans a string to be a valid filename or directory name."""
    # Remove characters not allowed in Windows/Linux filenames
    cleaned = re.sub(r'[\\/:*?"<>|]', '', filename).strip()
    # Replace leading/trailing dots or spaces (problematic in some OS)
    cleaned = re.sub(r'^\.|\.$', '', cleaned)
    cleaned = cleaned.strip()
    # Truncate to a reasonable length to avoid OS limits (e.g., 200 chars)
    if len(cleaned) > 200:
        cleaned = cleaned[:200]
    return cleaned

def extract_title_from_filename(filename, album_artist_name=None):
    """
    Attempts to extract the track title from a filename formatted as "Artist - Title.ext"
    or "Artist - Album - Title.ext" or "Title.ext".
    Prioritizes stripping artist/album if provided.
    """
    base_name = os.path.splitext(filename)[0]

    # Try to remove "Artist - " prefix if album_artist_name is known
    if album_artist_name:
        escaped_artist_name = re.escape(album_artist_name)
        # Regex to match "Artist - " at the beginning (case-insensitive, non-greedy)
        # This regex tries to capture the "Title" part after the first "Artist - " and optional "Album - "
        match = re.match(rf"^(?:{escaped_artist_name}\s*-\s*)?(?:[^\-]+?\s*-\s*)?(.*)$", base_name, re.IGNORECASE)
        if match:
            potential_title = match.group(1).strip()
            if potential_title:
                return potential_title

    # Fallback to general "Artist - Title" or "Title" parsing
    parts = [p.strip() for p in base_name.split(' - ')]
    if len(parts) >= 2:
        # Assume the last part is the title if multiple dashes are present
        return parts[-1]

    return base_name.strip()

def log(msg):
    if LOGGING_ENABLED:
        print(msg)