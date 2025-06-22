import requests
import json
from tqdm.asyncio import tqdm
import config # Import config for API_HEADERS, BASE_URL, QUALITY_MAP, SESSION_COOKIES
from utils import log
from config import QOBUZ_API_BASE_URLS

def try_endpoints(path, params=None, headers=None):
    last_exception = None
    for base_url in QOBUZ_API_BASE_URLS:
        url = f"{base_url}{path}"
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()  # Raises for 4xx/5xx
            return response
        except Exception as e:
            # Optionally log the failure here
            last_exception = e
            continue
    raise last_exception

def get_music_info(query, music_type="albums", offset=0, limit=10):
    """
    Searches for music (albums or tracks) and returns a list of dictionaries with their details.
    """
    path = f"/api/get-music"
    params = {"q": query, "offset": offset, "limit": limit}
    response = try_endpoints(path, params=params, headers=config.API_HEADERS)

    try:
        tqdm.write(f"Searching for {music_type} with query: '{query}'...")
        response.raise_for_status()

        data = response.json()

        if data.get("success") and data.get("data"):
            music_results = data["data"].get(music_type)
            if music_results and music_results.get("items"):
                tqdm.write(f"Found {music_results['total']} {music_results['total']} {music_type} for '{query}'.")

                processed_items = []
                for item in music_results["items"]:
                    item_id = item.get("id")
                    item_title = item.get("title", item.get("name", "N/A Title"))

                    item_artist = "N/A Artist"
                    if "artist" in item and "name" in item["artist"]:
                        item_artist = item["artist"]["name"]
                    elif "album_artist" in item:
                        item_artist = item["album_artist"]

                    determined_type = "album" if music_type == "albums" else "track"

                    item_release_date = item.get("release_date") or item.get("album", {}).get("release_date")

                    processed_items.append({
                        "id": item_id,
                        "title": item_title,
                        "artist": item_artist,
                        "type": determined_type,
                        "release_date": item_release_date,
                        "raw_data": item
                    })
                return processed_items
            else:
                tqdm.write(f"No {music_type} found for query: '{query}'")
                return []
        else:
            tqdm.write("Search request was not successful or data format is unexpected.")
            return []

    except requests.exceptions.RequestException as e:
        tqdm.write(f"Error during search: {e}")
        return []
    except json.JSONDecodeError:
        tqdm.write("Failed to decode JSON response from search.")
        return []

def get_album_details(album_id):
    """
    Fetches detailed information for a specific album, including its tracks.
    """
    path = "/api/get-album"
    params = {"album_id": album_id}
    for _ in range(len(config.QOBUZ_API_BASE_URLS)):
        try:
            api_url = f"{config.BASE_URL}{path}"
            response = requests.get(api_url, params=params, headers=config.API_HEADERS)
            if response.status_code == 502:
                config.switch_qobuz_api_url()
                continue
            response.raise_for_status()
            data = response.json()

            if data.get("success") and data.get("data"):
                album_data = data["data"]
                album_artist_name = album_data.get('artist', {}).get('name', 'N/A')
                tqdm.write(f"Album: {album_data.get('title', 'N/A')} by {album_artist_name}")

                tracks = []
                if album_data.get("tracks") and album_data["tracks"].get("items"):
                    tqdm.write("Tracks:")
                    for i, track_item in enumerate(album_data["tracks"]["items"]):
                        track_id = track_item.get("id")
                        track_title = track_item.get("title", "N/A Track Title")
                        track_artist = track_item.get("artist", {}).get("name", album_artist_name)

                        tracks.append({
                            "id": track_id,
                            "title": track_title,
                            "artist": track_artist,
                            "raw_data": track_item,
                            "track_number": i + 1 # Add track number from Qobuz order
                        })
                return album_data, tracks
            else:
                tqdm.write("Failed to get album details or data format is unexpected.")
                return None, []
        except requests.exceptions.RequestException as e:
            if hasattr(e.response, "status_code") and e.response.status_code == 502:
                config.switch_qobuz_api_url()
                continue
            print(f"Error fetching album details: {e}")
            return None, []
    print("All Qobuz endpoints failed.")
    return None, []

def get_qobuz_cdn_url(track_id, quality):
    import requests
    base_url = config.BASE_URL.rstrip("/")
    url = f"{base_url}/api/download-music"
    params = {
        "track_id": track_id,
        "quality": quality  # Use 27 for FLAC, 5 for MP3, etc.
    }
    headers = config.API_HEADERS
    try:
        print(f"Requesting CDN URL: {url} params={params}")
        response = requests.get(url, params=params, headers=headers)
        print(f"Response status: {response.status_code}, body: {response.text[:200]}")
        response.raise_for_status()
        data = response.json()
        # FIX: Extract the URL from the correct place
        return data.get("data", {}).get("url")
    except Exception as e:
        print(f"Error fetching Qobuz CDN URL from squid.wtf: {e}")
        return None