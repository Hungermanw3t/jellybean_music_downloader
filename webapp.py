from flask import Flask, request, render_template, redirect, url_for, session, flash
import asyncio
import os
import musicbrainzngs
from functools import wraps

import config
from qobuz_api import get_music_info, get_album_details
from downloader import main_download_orchestrator
from tagger import tag_file_with_musicbrainz_api, check_fpcalc_readiness, MusicBrainzRateLimiter
from utils import clean_filename
from release_matcher import ReleaseMatcher

app = Flask(__name__, static_folder='static')
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change_this_secret_key_in_production")

musicbrainzngs.set_useragent("QobuzSquidDownloader", "1.0", "your@email.com")

LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "1234")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def search_musicbrainz_releases(artist, album):
    try:
        result = musicbrainzngs.search_releases(artist=artist, release=album, limit=10)
        return result.get("release-list", [])
    except Exception as e:
        print(f"MusicBrainz search error: {e}")
        return []

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    return redirect(url_for("albums"))

@app.route("/albums", methods=["GET", "POST"])
@login_required
def albums():
    search_term = session.get("search_term", "")
    search_type = session.get("search_type", "albums")
    found_items = session.get("found_items", [])

    if request.method == "POST":
        action = request.form.get("action")
        if action == "search":
            search_term = request.form["search_term"]
            search_type = request.form["search_type"]
            found_items = get_music_info(search_term, music_type=search_type, limit=20)
            session["found_items"] = found_items
            session["search_term"] = search_term
            session["search_type"] = search_type
        elif action == "select":
            selected_album_idx = int(request.form["selected_album"])
            selected_album = session.get("found_items", [])[selected_album_idx]
            album_id = selected_album["id"]
            album_data, tracks = get_album_details(album_id)
            
            if album_data is None:
                flash("Failed to fetch album details. Please try again.")
                return redirect(url_for("albums"))
            
            session["selected_album"] = {
                "title": album_data.get("title", ""),
                "artist": album_data.get("artist", {}).get("name", "")
            }
            session["album_tracks"] = [
                {
                    "id": t.get("id"),
                    "title": t.get("title", "Unknown Title"),
                    "artist": t.get("artist", album_data.get("artist", {}).get("name", "Unknown Artist")),
                    "track_number": t.get("track_number")
                }
                for t in tracks
            ]
            session["selected_track_indices"] = list(range(len(tracks)))
            return redirect(url_for("select_mb_release"))

    return render_template(
        "albums.html",
        found_items=session.get("found_items", []),
        search_term=session.get("search_term", ""),
        search_type=session.get("search_type", "albums")
    )

@app.route("/select_mb_release", methods=["GET", "POST"])
@login_required
def select_mb_release():
    album = session.get("selected_album", {})
    artist = album.get("artist", "")
    title = album.get("title", "")
    
    # Try automatic release matching first
    matcher = ReleaseMatcher()
    tracks = session.get("album_tracks", [])
    track_count = len(tracks)
    
    # Try to get release year from Qobuz data if available
    release_year = None
    try:
        # This would need to be passed from the album selection
        # For now, we'll skip year matching
        pass
    except:
        pass
    
    auto_match = matcher.find_best_release(artist, title, track_count, release_year)
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "auto_select" and auto_match:
            # User confirmed automatic selection
            session["selected_mb_release_id"] = auto_match['id']
            return redirect(url_for("loading"))
        elif action == "manual_select":
            # User chose manual selection
            selected_mb_id = request.form.get("selected_mb_release")
            session["selected_mb_release_id"] = selected_mb_id
            return redirect(url_for("loading"))
        else:
            # Regular manual selection
            selected_mb_id = request.form.get("selected_mb_release")
            session["selected_mb_release_id"] = selected_mb_id
            return redirect(url_for("loading"))
    
    # Get manual options for fallback
    releases = search_musicbrainz_releases(artist, title)
    
    return render_template(
        "select_release.html", 
        releases=releases, 
        album=album,
        auto_match=auto_match
    )

@app.route("/loading")
@login_required
def loading():
    return render_template("loading.html")

@app.route("/downloading")
@login_required
def downloading():
    tracks = session.get("album_tracks", [])
    selected_indices = session.get("selected_track_indices", [])
    selected_mb_release_id = session.get("selected_mb_release_id")
    
    if not selected_indices:
        flash("Please select at least one track.")
        return redirect(url_for("albums"))
    
    items_to_download = [tracks[idx] for idx in selected_indices]
    album = session.get("selected_album", {})
    artist = clean_filename(album.get("artist", "Unknown Artist"))
    title = clean_filename(album.get("title", "Unknown Album"))
    folder_name = f"{artist} - {title}"
    current_download_dir = os.path.join(config.DOWNLOAD_BASE_DIR, folder_name)
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            download_and_tag_all(
                items_to_download,
                current_download_dir,
                selected_mb_release_id
            )
        )
        loop.close()
        flash("Download and tagging complete!")
    except Exception as e:
        flash(f"Error: {e}")
    
    return redirect(url_for("done"))

@app.route("/done")
@login_required
def done():
    # Clear search results when download is complete
    session.pop("found_items", None)
    session.pop("search_term", None)
    session.pop("search_type", None)
    session.pop("selected_album", None)
    session.pop("album_tracks", None)
    session.pop("selected_track_indices", None)
    session.pop("selected_mb_release_id", None)
    return render_template("done.html")

async def download_and_tag_all(items_to_download, current_download_dir, selected_mb_release_id=None):
    file_ready_queue = asyncio.Queue()
    rate_limiter = MusicBrainzRateLimiter(min_interval=1.0)
    
    await main_download_orchestrator(
        items_to_download,
        "FLAC",
        current_download_dir,
        file_ready_queue=file_ready_queue
    )
    
    downloaded_files = []
    while not file_ready_queue.empty():
        downloaded_files.append(await file_ready_queue.get())
    
    acoustid_is_ready = config.ACOUSTID_API_KEY != "YOUR_ACOUSTID_API_KEY_HERE"
    fpcalc_ready_status = check_fpcalc_readiness()
    
    for file_info in downloaded_files:
        audio_file_path, file_download_format = file_info
        filename_only = os.path.basename(audio_file_path)
        track_data_for_this_file = None
        
        for q_track_data in items_to_download:
            expected_filename = f"{clean_filename(q_track_data['artist'])} - {clean_filename(q_track_data['title'])}.{file_download_format.lower()}"
            if expected_filename == filename_only:
                track_data_for_this_file = q_track_data
                break
        
        await rate_limiter.wait()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            tag_file_with_musicbrainz_api,
            audio_file_path,
            None,
            track_data_for_this_file,
            acoustid_is_ready,
            fpcalc_ready_status,
            selected_mb_release_id
        )

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        if request.form.get("password") == LOGIN_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        else:
            error = "Incorrect password."
    return render_template("login.html", error=error)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.getenv("FLASK_DEBUG", "0") == "1")