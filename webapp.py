from flask import Flask, request, render_template_string, redirect, url_for, session, flash
import asyncio
import config
from qobuz_api import get_music_info, get_album_details
from downloader import main_download_orchestrator
from tagger import tag_file_with_musicbrainz_api, check_fpcalc_readiness, tag_file_worker, MusicBrainzRateLimiter
from utils import clean_filename
import os
import musicbrainzngs

app = Flask(__name__)
app.secret_key = "change_this_secret"  # Needed for session

musicbrainzngs.set_useragent("QobuzSquidDownloader", "1.0", "your@email.com")

def search_musicbrainz_releases(artist, album):
    try:
        result = musicbrainzngs.search_releases(artist=artist, release=album, limit=10)
        return result.get("release-list", [])
    except Exception as e:
        print(f"MusicBrainz search error: {e}")
        return []

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        search_term = request.form["search_term"]
        search_type = request.form["search_type"]
        found_items = get_music_info(search_term, music_type=search_type, limit=20)
        session["found_items"] = found_items
        session["search_term"] = search_term
        session["search_type"] = search_type
        return redirect(url_for("albums"))
    return render_template_string(TEMPLATE_SEARCH)

@app.route("/albums", methods=["GET", "POST"])
def albums():
    found_items = session.get("found_items", [])
    search_term = session.get("search_term", "")
    if request.method == "POST":
        selected_album_idx = int(request.form["selected_album"])
        selected_album = found_items[selected_album_idx]
        album_id = selected_album["id"]
        album_data, tracks = get_album_details(album_id)
        # Use album_data from API for correct artist/title
        for t in tracks:
            t.setdefault('artist', album_data.get('artist', {}).get('name', 'Unknown Artist'))
            t.setdefault('title', t.get('title', 'Unknown Title'))
            t.setdefault('id', t.get('id'))
        print("Tracks fetched:", tracks)  # Debug
        # Only store minimal album info
        session["selected_album"] = {
            "title": album_data.get("title", ""),
            "artist": album_data.get("artist", {}).get("name", "")
        }
        # Only store minimal track info
        session["album_tracks"] = [
            {
                "id": t.get("id"),
                "title": t.get("title"),
                "artist": t.get("artist"),
                "track_number": t.get("track_number")
            }
            for t in tracks
        ]
        return redirect(url_for("tracks"))
    return render_template_string(TEMPLATE_ALBUMS, found_items=found_items, search_term=search_term)

@app.route("/tracks", methods=["GET", "POST"])
def tracks():
    tracks = session.get("album_tracks", [])
    selected_album = session.get("selected_album", {})
    if request.method == "POST":
        if "download_all" in request.form:
            selected_indices = list(range(len(tracks)))
        else:
            selected_indices = [int(idx) for idx in request.form.getlist("selected_index")]
        if not selected_indices:
            flash("Please select at least one track.")
            return redirect(url_for("tracks"))
        session["selected_track_indices"] = selected_indices
        return redirect(url_for("select_mb_release"))  # <-- Redirect here
    return render_template_string(TEMPLATE_TRACKS, tracks=tracks, album=selected_album)

@app.route("/select_mb_release", methods=["GET", "POST"])
def select_mb_release():
    album = session.get("selected_album", {})
    artist = album.get("artist", "")
    title = album.get("title", "")
    releases = search_musicbrainz_releases(artist, title)
    if request.method == "POST":
        selected_mb_id = request.form.get("selected_mb_release")
        session["selected_mb_release_id"] = selected_mb_id
        return redirect(url_for("loading"))  # <-- Redirect to loading
    return render_template_string(TEMPLATE_MB_RELEASES, releases=releases, album=album)

TEMPLATE_LOADING = """
<h1>Processing...</h1>
<p>Your tracks are being downloaded and tagged. This may take a minute. Please wait...</p>
<script>
fetch("{{ url_for('loading_start') }}", {method: "POST"})
  .then(() => window.location = "{{ url_for('done') }}");
</script>
"""

@app.route("/loading")
def loading():
    return render_template_string(TEMPLATE_LOADING)

@app.route("/done")
def done():
    return render_template_string(TEMPLATE_DONE)

def download_and_tag_all(
    items_to_download,
    download_format,
    current_download_dir,
    qobuz_album_data_for_tagging,
    acoustid_is_ready,
    fpcalc_ready_status
):
    async def inner():
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
        # --- Get the selected MusicBrainz release ID from session ---
        selected_mb_release_id = session.get("selected_mb_release_id")
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
            # --- Pass selected_mb_release_id to the tagger ---
            await loop.run_in_executor(
                None,
                tag_file_with_musicbrainz_api,
                audio_file_path,
                qobuz_album_data_for_tagging,
                track_data_for_this_file,
                acoustid_is_ready,
                fpcalc_ready_status,
                selected_mb_release_id  # <-- Add this argument
            )
    return inner()

# --- Templates ---

TEMPLATE_SEARCH = """
<h1>Qobuz Squid Downloader Web UI</h1>
<form method="post">
    <input name="search_term" placeholder="Search term" required>
    <select name="search_type">
        <option value="albums">Albums</option>
        <option value="tracks">Tracks</option>
    </select>
    <button type="submit">Search</button>
</form>
"""

TEMPLATE_ALBUMS = """
<h1>Albums for '{{search_term}}'</h1>
<form method="post">
<ul>
{% for item in found_items %}
    <li>
        <input type="radio" name="selected_album" value="{{loop.index0}}" required>
        {{item['artist']}} - {{item['title']}}
    </li>
{% endfor %}
</ul>
<button type="submit">Select Album</button>
</form>
<a href="{{url_for('index')}}">Back to search</a>
"""

TEMPLATE_TRACKS = """
<h1>Tracks for '{{album.get('artist', '')}} - {{album.get('title', '')}}'</h1>
<form method="post">
<ul>
{% for track in tracks %}
    <li>
        <input type="checkbox" name="selected_index" value="{{loop.index0}}">
        {{track['artist']}} - {{track['title']}}
    </li>
{% endfor %}
</ul>
<button type="submit">Download & Tag Selected</button>
<button type="submit" name="download_all" value="1">Download & Tag All</button>
</form>
<a href="{{url_for('albums')}}">Back to albums</a>
"""

TEMPLATE_MB_RELEASES = """
<h1>Select MusicBrainz Release for '{{album['artist']}} - {{album['title']}}'</h1>
<form method="post">
<ul>
{% for release in releases %}
    <li>
        <input type="radio" name="selected_mb_release" value="{{release['id']}}" required>
        {{release['title']}} ({{release['date'] if release.get('date') else 'Unknown Year'}}) - {{release['country'] if release.get('country') else 'Unknown Country'}}
    </li>
{% endfor %}
</ul>
<button type="submit">Use Selected Release</button>
</form>
<a href="{{url_for('tracks')}}">Back to tracks</a>
"""

TEMPLATE_DONE = """
<h1>Done!</h1>
<p>{{ get_flashed_messages()[0] if get_flashed_messages() else '' }}</p>
<a href="{{url_for('index')}}">Back to search</a>
"""

@app.route("/loading/start", methods=["POST"])
def loading_start():
    tracks = session.get("album_tracks", [])
    selected_indices = session.get("selected_track_indices", [])
    if not selected_indices or any(idx >= len(tracks) for idx in selected_indices):
        flash("Please select at least one track.")
        return "", 400
    items_to_download = [tracks[idx] for idx in selected_indices]
    download_format = "FLAC"
    album = session.get("selected_album", {})
    artist = clean_filename(album.get("artist", "Unknown Artist"))
    title = clean_filename(album.get("title", "Unknown Album"))
    folder_name = f"{artist} - {title}"
    current_download_dir = os.path.join(config.DOWNLOAD_BASE_DIR, folder_name)
    qobuz_album_data_for_tagging = None
    acoustid_is_ready = config.ACOUSTID_API_KEY != "YOUR_ACOUSTID_API_KEY_HERE" and bool(config.ACOUSTID_API_KEY)
    fpcalc_ready_status = check_fpcalc_readiness()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            download_and_tag_all(
                items_to_download,
                download_format,
                current_download_dir,
                qobuz_album_data_for_tagging,
                acoustid_is_ready,
                fpcalc_ready_status
            )
        )
        flash("Download and tagging complete!")
    except Exception as e:
        flash(f"Error: {e}")
    finally:
        loop.close()
    return "", 204  # No Content

if __name__ == "__main__":
    os.makedirs(config.DOWNLOAD_BASE_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=True)