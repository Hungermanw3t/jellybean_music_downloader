import os
import asyncio
import aiohttp
from tqdm.asyncio import tqdm

from qobuz_api import get_qobuz_cdn_url
from utils import clean_filename, log
import config # Import config for DOWNLOAD_BASE_DIR, QOBUZ_CDN_DOWNLOAD_HEADERS
from config import TRANSCODE_MAP
from transcoder import transcode
import functools

async def download_music_async(qobuz_cdn_url, output_filename, requested_format="FLAC", target_directory=config.DOWNLOAD_BASE_DIR, overall_pbar=None, file_ready_queue=None, download_format=None):
    """
    Downloads the music file directly from the Qobuz CDN URL asynchronously.
    Includes progress bar using tqdm.
    """
    if not qobuz_cdn_url:
        return None

    download_headers = config.QOBUZ_CDN_DOWNLOAD_HEADERS.copy()
    format_info = TRANSCODE_MAP.get(requested_format.upper(), TRANSCODE_MAP["FLAC"])
    download_format = format_info["download"]
    output_ext = format_info["ext"]

    if requested_format.lower() in ("flac", "hi-res"):
        download_headers["Accept"] = "audio/flac, */*"
    elif requested_format.lower().startswith("mp3"):
        download_headers["Accept"] = "audio/mpeg, */*"
    elif requested_format.lower() == "alac":
        download_headers["Accept"] = "audio/x-m4a, */*"
    else:
        download_headers["Accept"] = "*/*"

    os.makedirs(target_directory, exist_ok=True)
    temp_path = os.path.join(target_directory, output_filename + ".tmp")
    final_path = os.path.splitext(os.path.join(target_directory, output_filename))[0] + f".{output_ext}"

    try:
        async with aiohttp.ClientSession(headers=download_headers) as session:
            async with session.get(qobuz_cdn_url) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                with open(temp_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                        if overall_pbar:
                            overall_pbar.update(len(chunk))
        # After download, handle transcoding or renaming
        if download_format.lower() == output_ext:
            # No transcoding needed, just rename
            os.rename(temp_path, final_path)
            if file_ready_queue:
                await file_ready_queue.put((final_path, download_format))
            return final_path
        else:
            # Transcoding needed
            success = transcode(temp_path, final_path)
            if success:
                os.remove(temp_path)
                if file_ready_queue:
                    await file_ready_queue.put((final_path, download_format))
                return final_path
            else:
                tqdm.write(f"Transcoding failed for {temp_path}")
                return None
    except aiohttp.ClientError as e:
        tqdm.write(f"Error during download of '{output_filename}': {e}")
        return None
    except Exception as e:
        tqdm.write(f"An unexpected error occurred during download of '{output_filename}': {e}")
        return None

async def fetch_file_size(session, url):
    try:
        async with session.head(url) as resp:
            return int(resp.headers.get('content-length', 0))
    except Exception:
        return 0

async def main_download_orchestrator(items_to_download, download_format, current_download_dir, file_ready_queue=None):
    download_tasks = []
    file_infos = []
    urls_and_filenames = []

    quality = config.QUALITY_MAP.get(download_format.upper(), 27)

    for track_num, track_item in enumerate(items_to_download, 1):
        if not track_item.get("id"):
            log(f"Skipping '{track_item.get('title', 'Unknown Track')}' as it has no ID.")
            continue
        log(f"Preparing download task for: {track_item['artist']} - {track_item['title']}")
        qobuz_cdn_url = get_qobuz_cdn_url(track_item['id'], quality)
        if qobuz_cdn_url:
            clean_title = clean_filename(track_item['title'])
            clean_artist = clean_filename(track_item['artist'])
            # You still need the format for file extension
            ext = download_format.lower() if download_format.upper() != "ALAC" else "m4a"
            output_filename = f"{clean_artist} - {clean_title}.{ext}"
            urls_and_filenames.append((qobuz_cdn_url, output_filename))
        else:
            log(f"Failed to get Qobuz CDN URL for '{track_item['title']}'. This track will not be downloaded.")

    if not urls_and_filenames:
        print("No valid download tasks were created.")
        return False

    # Batch HEAD requests for file sizes (no progress bar)
    async with aiohttp.ClientSession() as session:
        size_tasks = [fetch_file_size(session, url) for url, _ in urls_and_filenames]
        sizes = await asyncio.gather(*size_tasks)

    total_bytes = sum(sizes)
    file_infos = [(url, filename, size) for (url, filename), size in zip(urls_and_filenames, sizes)]

    log(f"\n--- Starting {len(file_infos)} concurrent downloads ---")
    # REMOVE this overall progress bar too:
    # with tqdm(total=total_bytes, unit='B', unit_scale=True, desc="Total Progress") as overall_pbar:
    #     for qobuz_cdn_url, output_filename, _ in file_infos:
    #         task = download_music_async(...)
    #         download_tasks.append(task)
    #     await asyncio.gather(*download_tasks)
    # log("\nAll concurrent downloads completed.")
    # return True

    # INSTEAD, just run the downloads without a progress bar:
    for qobuz_cdn_url, output_filename, _ in file_infos:
        task = download_music_async(
            qobuz_cdn_url, output_filename,
            requested_format=download_format,
            target_directory=current_download_dir,
            overall_pbar=None,
            file_ready_queue=file_ready_queue,
            download_format=download_format
        )
        download_tasks.append(task)
    await asyncio.gather(*download_tasks)
    log("\nAll concurrent downloads completed.")
    return True