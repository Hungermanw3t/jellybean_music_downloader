import os
import asyncio
import sys
import subprocess
import requests
import time
import re
import concurrent.futures
from tqdm import tqdm

# Import functions from our new modules
import config
from qobuz_api import get_music_info, get_album_details
from downloader import main_download_orchestrator
from tagger import tag_file_with_musicbrainz_api, check_fpcalc_readiness, tag_file_worker, MusicBrainzRateLimiter
from utils import clean_filename, log

# Global variable for fpcalc readiness
_fpcalc_ready_status = False

async def main_async():
    global _fpcalc_ready_status # Declare global to modify it

    print("Welcome to the Qobuz Squid Downloader!")
    os.makedirs(config.DOWNLOAD_BASE_DIR, exist_ok=True)

    # Validate AcoustID API key at startup
    if config.ACOUSTID_API_KEY == "YOUR_ACOUSTID_API_KEY_HERE" or not config.ACOUSTID_API_KEY:
        print("\n--- CRITICAL: ACOUSTID API KEY MISSING ---")
        print("To enable automatic MusicBrainz tagging, please get an API key from:")
        print("  https://acoustid.org/api-key")
        print("And paste it into the 'ACOUSTID_API_KEY' variable in your config.py file or set it as an environment variable.")
        print("Without it, AcoustID fallback for tagging will be skipped.")
        input("Press Enter to continue without AcoustID tagging, or Ctrl+C to exit and add the key.")
        acoustid_is_ready = False
    else:
        acoustid_is_ready = True

    # Check fpcalc readiness once
    _fpcalc_ready_status = check_fpcalc_readiness()

    while True:
        search_term = input("Enter search query (e.g., 'Daft Punk Discovery') or 'quit' to exit: ").strip()
        if search_term.lower() == 'quit':
            break

        search_type_choice = input("Search for (A)lbums or (T)racks? (A/T): ").strip().lower()
        if search_type_choice == 'a':
            search_type = "albums"
        elif search_type_choice == 't':
            search_type = "tracks"
        else:
            print("Invalid choice. Defaulting to albums.")
            search_type = "albums"

        found_items = get_music_info(search_term, music_type=search_type, limit=20)

        if found_items:
            print("\n--- Search Results ---")
            for i, item in enumerate(found_items):
                print(f"{i+1}. Type: {item['type'].capitalize()}")
                print(f"   Title: {item['title']}")
                print(f"   Artist: {item['artist']}")
                if item['release_date']:
                    print(f"   Release Date: {item['release_date']}")
                print("-" * 30)

            while True:
                try:
                    selection = input(f"Enter the number of the {search_type.rstrip('s')} to select (1-{len(found_items)}), or 0 to search again: ").strip()
                    selected_index = int(selection) - 1

                    if selected_index == -1:
                        print("Searching again...\n")
                        break
                    elif 0 <= selected_index < len(found_items):
                        selected_item = found_items[selected_index]
                        selected_item_id = selected_item.get("id")

                        if selected_item_id:
                            print(f"\nYou selected: {selected_item['artist']} - {selected_item['title']} (ID: {selected_item_id})")

                            items_to_download = []
                            current_download_dir = config.DOWNLOAD_BASE_DIR
                            qobuz_album_data_for_tagging = None # Will hold full Qobuz album data if an album was selected

                            if selected_item['type'] == 'album':
                                album_details_data, album_tracks = get_album_details(selected_item_id)

                                if album_details_data:
                                    album_artist_name = album_details_data.get('artist', {}).get('name', selected_item['artist'])
                                    album_title = album_details_data.get('title', selected_item['title'])

                                    album_folder_name = clean_filename(f"{album_artist_name} - {album_title}")
                                    current_download_dir = os.path.join(config.DOWNLOAD_BASE_DIR, album_folder_name)
                                    os.makedirs(current_download_dir, exist_ok=True)
                                    print(f"Downloads for this album will go into: '{current_download_dir}'")
                                    qobuz_album_data_for_tagging = album_details_data


                                if album_tracks:
                                    print("\n--- Album Tracks ---")
                                    for i, track in enumerate(album_tracks):
                                        print(f"{i+1}. {track['artist']} - {track['title']} (ID: {track['id']})")

                                    while True:
                                        track_selection = input(f"Enter track number to download (1-{len(album_tracks)}), 'all' for all tracks, or 0 to go back to album selection: ").strip().lower()

                                        if track_selection == 'all':
                                            items_to_download = album_tracks
                                            break
                                        try:
                                            selected_track_index = int(track_selection) - 1

                                            if selected_track_index == -1:
                                                print("Going back to album selection.\n")
                                                break
                                            elif 0 <= selected_track_index < len(album_tracks):
                                                items_to_download.append(album_tracks[selected_track_index])
                                                break
                                            else:
                                                print(f"Invalid track selection. Please enter a number between 1 and {len(album_tracks)}, 'all', or 0.")
                                        except ValueError:
                                            print("Invalid input. Please enter a number, 'all', or 0.")
                                        except Exception as e:
                                            print(f"An unexpected error occurred during track selection: {e}")
                                else:
                                    print("No tracks found for this album.")
                                    break

                                if items_to_download and qobuz_album_data_for_tagging:
                                    print("\n--- Selecting MusicBrainz Release for this Album ---")

                                    print(f"Searching MusicBrainz for releases of '{album_title}' by '{album_artist_name}'...")
                                    mb_release_search_url = "https://musicbrainz.org/ws/2/release/"
                                    mb_release_search_params = {
                                        "fmt": "json",
                                        "query": f"release:{album_title} AND artist:{album_artist_name}",
                                        "inc": "release-groups+artists+labels+media",
                                        "limit": 25
                                    }
                                    mb_headers = {"User-Agent": config.MUSICBRAINZ_USER_AGENT}

                                    try:
                                        mb_release_search_response = requests.get(mb_release_search_url, params=mb_release_search_params, headers=mb_headers)
                                        mb_release_search_response.raise_for_status()
                                        mb_release_search_data = mb_release_search_response.json()
                                        config.SESSION_COOKIES.update(mb_release_search_response.cookies.get_dict()) # Example: Capture cookies if needed
                                        time.sleep(1) # Be nice to MusicBrainz API

                                        available_releases = mb_release_search_data.get('releases', [])

                                        if available_releases:
                                            print("\n--- Found MusicBrainz Releases ---")
                                            display_releases = []
                                            for i, r in enumerate(available_releases):
                                                release_title = r.get('title', 'N/A Title')
                                                release_artist = r.get('artist-credit', [{}])[0].get('name', 'N/A Artist')
                                                release_date = r.get('date', 'N/A Date')
                                                release_country = r.get('country', 'N/A Country')
                                                release_status = r.get('status', 'N/A Status')
                                                release_type = r.get('release-group', {}).get('primary-type', 'N/A Type')

                                                # Remove bracketed text from artist name for display
                                                display_artist = re.sub(r' \[.+?\]', '', release_artist)

                                                display_releases.append(r)
                                                print(f"{len(display_releases)}. Title: {release_title}")
                                                print(f"   Artist: {display_artist}")
                                                print(f"   Date: {release_date}, Country: {release_country}, Status: {release_status}, Type: {release_type}")
                                                print(f"   MBID: {r.get('id')}")
                                                print("-" * 30)

                                            while True:
                                                try:
                                                    release_choice = input(f"Enter the number of the MusicBrainz Release to use for tagging (1-{len(display_releases)}), or 0 to skip tagging for this album: ").strip()
                                                    chosen_release_index = int(release_choice) - 1

                                                    if chosen_release_index == -1:
                                                        print("Skipping MusicBrainz tagging for this album.")
                                                        qobuz_album_data_for_tagging = None # Effectively skip MB tagging for album
                                                        break
                                                    elif 0 <= chosen_release_index < len(display_releases):
                                                        chosen_mb_release = display_releases[chosen_release_index]
                                                        config._album_release_cache[qobuz_album_data_for_tagging['id']] = chosen_mb_release['id']
                                                        print(f"Selected MusicBrainz Release: {chosen_mb_release['title']} ({chosen_mb_release['id']})")
                                                        break
                                                    else:
                                                        print(f"Invalid choice. Please enter a number between 1 and {len(display_releases)}, or 0.")
                                                except ValueError:
                                                    print("Invalid input. Please enter a number.")
                                                except Exception as e:
                                                    print(f"An unexpected error occurred during MusicBrainz release selection: {e}")
                                        else:
                                            print(f"No MusicBrainz releases found for '{album_title}' by '{album_artist_name}'. Tagging will proceed with basic track data only, or AcoustID if enabled.")
                                            qobuz_album_data_for_tagging = None # Skip album-level MB lookup
                                    except requests.exceptions.RequestException as e:
                                        print(f"Error searching MusicBrainz for releases: {e}. Tagging will proceed with basic track data only, or AcoustID if enabled.")
                                        qobuz_album_data_for_tagging = None
                                    except Exception as e:
                                        print(f"An unexpected error occurred during MusicBrainz release search: {e}. Tagging will proceed with basic track data only, or AcoustID if enabled.")
                                        qobuz_album_data_for_tagging = None
                                else: # if items_to_download but no qobuz_album_data_for_tagging (e.g. if skipped selection)
                                    print("Skipping MusicBrainz release selection for tagging as no album data or items to download.")


                            elif selected_item['type'] == 'track':
                                items_to_download.append(selected_item)
                                track_album_data = selected_item['raw_data'].get('album')
                                if track_album_data:
                                    album_artist_name = track_album_data.get('artist', {}).get('name', selected_item['artist'])
                                    album_title = track_album_data.get('title', 'Unknown Album')

                                    album_folder_name = clean_filename(f"{album_artist_name} - {album_title}")
                                    current_download_dir = os.path.join(config.DOWNLOAD_BASE_DIR, album_folder_name)
                                    os.makedirs(current_download_dir, exist_ok=True)
                                    print(f"Single track download will go into: '{current_download_dir}'")
                                    qobuz_album_data_for_tagging = track_album_data
                                else:
                                    print("Could not find album information for this track. Saving to base download directory.")
                                    qobuz_album_data_for_tagging = None

                            else:
                                print("Unknown item type. Cannot proceed with download.")
                                break

                            # --- Moved download_format input outside of the album/track specific blocks ---
                            if items_to_download: # Only ask for format if there are items to download
                                download_format = input("Enter desired download format (e.g., FLAC, MP3, ALAC): ").strip().upper()

                                downloads_successful = await download_and_tag_all(
                                    items_to_download,
                                    download_format,
                                    current_download_dir,
                                    qobuz_album_data_for_tagging,
                                    acoustid_is_ready,
                                    _fpcalc_ready_status
                                )
                                print(f"\nDownload and tagging complete for {len(items_to_download)} file(s) in '{current_download_dir}'.")
                                input("Press Enter to return to search...")
                                break  # Exit album/track selection loop
                            else:
                                print("No tracks selected for download.")
                                break

                        else:
                            print("Selected item has no ID. Cannot proceed with download.")
                            print("Please choose another item or search again.")
                    else:
                        print(f"Invalid selection. Please enter a number between 1 and {len(found_items)}.")
                except ValueError:
                    print("Invalid input. Please enter a number.")
                except Exception as e:
                    print(f"An unexpected error occurred: {e}")

    print("Exiting program.")

async def download_and_tag_all(
    items_to_download,
    download_format,
    current_download_dir,
    qobuz_album_data_for_tagging,
    acoustid_is_ready,
    fpcalc_ready_status
):
    file_ready_queue = asyncio.Queue()
    rate_limiter = MusicBrainzRateLimiter(min_interval=1.0)
    num_files = len(items_to_download)

    # --- Download all files first ---
    await main_download_orchestrator(
        items_to_download,
        download_format,
        current_download_dir,
        file_ready_queue=file_ready_queue
    )

    # --- Prepare list of downloaded files for tagging ---
    downloaded_files = []
    while not file_ready_queue.empty():
        downloaded_files.append(await file_ready_queue.get())

    # --- Tagging progress bar ---
    for file_info in downloaded_files:
        audio_file_path, download_format = file_info
        filename_only = os.path.basename(audio_file_path)
        track_data_for_this_file = None
        for q_track_data in items_to_download:
            expected_filename = f"{clean_filename(q_track_data['artist'])} - {clean_filename(q_track_data['title'])}.{download_format.lower()}"
            if expected_filename == filename_only:
                track_data_for_this_file = q_track_data
                break
        await rate_limiter.wait()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            tag_file_with_musicbrainz_api,
            audio_file_path,
            qobuz_album_data_for_tagging,
            track_data_for_this_file,
            acoustid_is_ready,
            fpcalc_ready_status
        )