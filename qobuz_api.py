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

def get_music_info_with_fallback(query, music_type="albums", offset=0, limit=10):
    """
    Enhanced search that tries multiple strategies and fallbacks.
    """
    all_results = []
    
    # First try the existing squid.wtf method with pagination to get more results
    try:
        # Try multiple pages to get more results
        for page_offset in [0, limit, limit*2]:
            results = get_music_info(query, music_type, page_offset, limit)
            if results:
                all_results.extend(results)
                if len(all_results) >= limit:
                    break
            else:
                break  # No more results
        
        if all_results:
            # Remove duplicates based on ID
            seen_ids = set()
            unique_results = []
            for item in all_results:
                if item.get('id') not in seen_ids:
                    unique_results.append(item)
                    seen_ids.add(item.get('id'))
            
            tqdm.write(f"Found {len(unique_results)} unique results using squid.wtf proxy")
            return unique_results[:limit]  # Limit to requested number
            
    except Exception as e:
        tqdm.write(f"Squid.wtf search failed: {e}")
    
    # Fallback: Try direct Qobuz web search (public endpoint)
    try:
        tqdm.write("Trying direct Qobuz search as fallback...")
        results = search_qobuz_direct(query, music_type, limit)
        if results:
            tqdm.write(f"Found {len(results)} results using direct Qobuz search")
            return results
    except Exception as e:
        tqdm.write(f"Direct Qobuz search failed: {e}")
    
    # Try different search term variations
    try:
        # Try with different variations of the search term
        search_variations = generate_search_variations(query)
        for variation in search_variations:
            tqdm.write(f"Trying search variation: '{variation}'")
            results = get_music_info(variation, music_type, offset, limit)
            if results:
                tqdm.write(f"Found {len(results)} results with variation '{variation}'")
                return results
    except Exception as e:
        tqdm.write(f"Search variations failed: {e}")
    
    tqdm.write("All search methods failed")
    return []

def search_qobuz_direct(query, music_type="albums", limit=10):
    """
    Try to search using Qobuz's public web search endpoint (if available).
    """
    # This is a simplified attempt at direct Qobuz search
    # Note: This may not work depending on Qobuz's current API restrictions
    base_url = "https://www.qobuz.com"
    search_url = f"{base_url}/api.json/0.2/catalog/search"
    
    params = {
        "query": query,
        "type": music_type,
        "limit": limit,
        "app_id": "285473059",  # Public app ID (may need updating)
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.qobuz.com/"
    }
    
    response = requests.get(search_url, params=params, headers=headers, timeout=10)
    response.raise_for_status()
    
    data = response.json()
    
    # Process the results to match our expected format
    results = []
    if music_type == "albums" and "albums" in data:
        for item in data["albums"]["items"][:limit]:
            results.append({
                "id": item.get("id"),
                "title": item.get("title", "Unknown Title"),
                "artist": item.get("artist", {}).get("name", "Unknown Artist"),
                "type": "album",
                "release_date": item.get("released_at"),
                "raw_data": item
            })
    elif music_type == "tracks" and "tracks" in data:
        for item in data["tracks"]["items"][:limit]:
            results.append({
                "id": item.get("id"),
                "title": item.get("title", "Unknown Title"),
                "artist": item.get("performer", {}).get("name", "Unknown Artist"),
                "type": "track",
                "release_date": item.get("album", {}).get("released_at"),
                "raw_data": item
            })
    
    return results

def generate_search_variations(query):
    """
    Generate different search term variations to improve search success.
    """
    variations = []
    
    # Original query
    variations.append(query)
    
    # Remove common words that might interfere
    stop_words = ["the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"]
    words = query.lower().split()
    filtered_words = [word for word in words if word not in stop_words]
    if len(filtered_words) < len(words):
        variations.append(" ".join(filtered_words))
    
    # Try with quotes for exact match
    if len(query.split()) > 1:
        variations.append(f'"{query}"')
    
    # Try individual words if it's a multi-word query
    if len(words) > 1:
        for word in words:
            if len(word) > 3:  # Only try meaningful words
                variations.append(word)
    
    # Try without punctuation
    import re
    clean_query = re.sub(r'[^\w\s]', '', query)
    if clean_query != query:
        variations.append(clean_query)
    
    return variations[:5]  # Limit to 5 variations to avoid too many requests