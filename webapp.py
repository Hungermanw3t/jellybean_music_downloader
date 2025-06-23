from flask import Flask, request, render_template_string, redirect, url_for, session, flash
import asyncio
import config
from qobuz_api import get_music_info, get_album_details
from downloader import main_download_orchestrator
from tagger import tag_file_with_musicbrainz_api, check_fpcalc_readiness, tag_file_worker, MusicBrainzRateLimiter
from utils import clean_filename
import os
import musicbrainzngs
from functools import wraps

app = Flask(__name__)
app.secret_key = "change_this_secret"  # Needed for session

musicbrainzngs.set_useragent("QobuzSquidDownloader", "1.0", "your@email.com")

LOGIN_PASSWORD = "1234"

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
            selected_album = found_items[selected_album_idx]
            album_id = selected_album["id"]
            album_data, tracks = get_album_details(album_id)
            for t in tracks:
                t.setdefault('artist', album_data.get('artist', {}).get('name', 'Unknown Artist'))
                t.setdefault('title', t.get('title', 'Unknown Title'))
                t.setdefault('id', t.get('id'))
            session["selected_album"] = {
                "title": album_data.get("title", ""),
                "artist": album_data.get("artist", {}).get("name", "")
            }
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

    return render_template_string(
        TEMPLATE_SEARCH_AND_ALBUMS,
        found_items=found_items,
        search_term=search_term,
        search_type=search_type
    )

@app.route("/tracks", methods=["GET", "POST"])
@login_required
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
@login_required
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

@app.route("/loading")
@login_required
def loading():
    return render_template_string(TEMPLATE_LOADING)

@app.route("/done")
@login_required
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

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        if request.form.get("password") == LOGIN_PASSWORD:
            session["authenticated"] = True
            return redirect(url_for("index"))
        else:
            error = "Incorrect password."
    return render_template_string(TEMPLATE_LOGIN, error=error)

@app.route("/loading/start", methods=["POST"])
@login_required
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

# --- Templates (move these up, before any route functions that use them) ---

TEMPLATE_LOADING = """
<h1>Processing...</h1>
<p>Your tracks are being downloaded and tagged. This may take a minute. Please wait...</p>
<script>
fetch("{{ url_for('loading_start') }}", {method: "POST"})
  .then(() => window.location = "{{ url_for('done') }}");
</script>
"""

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

TEMPLATE_SEARCH_AND_ALBUMS = """
<h1>Qobuz Squid Downloader Web UI</h1>
<form method="post" id="searchForm" style="margin-bottom: 32px;">
    <input name="search_term" placeholder="Search term" required value="{{search_term|default('')}}">
    <select name="search_type">
        <option value="albums" {% if search_type == 'albums' %}selected{% endif %}>Albums</option>
        <option value="tracks" {% if search_type == 'tracks' %}selected{% endif %}>Tracks</option>
    </select>
    <button type="submit" name="action" value="search">Search</button>
</form>

{% if found_items %}
<form method="post" id="albumForm">
    <div style="display: flex; flex-wrap: wrap; gap: 32px; justify-content: flex-start;">
    {% for item in found_items %}
        {% set album_id = item['id'] %}
        {% set seg1 = album_id[-2:] %}
        {% set seg2 = album_id[-4:-2] %}
        {% set img_url = 'https://static.qobuz.com/images/covers/' ~ seg1 ~ '/' ~ seg2 ~ '/' ~ album_id ~ '_230.jpg' %}
        <label class="album-card" style="
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            width: 200px;
            background: #18181b;
            border-radius: 12px;
            padding: 0;
            cursor: pointer;
            box-shadow: none;
            transition: box-shadow 0.2s, border 0.2s;
            border: 2px solid transparent;
            ">
            <input type="radio" name="selected_album" value="{{loop.index0}}" required style="display:none;">
            <img src="{{img_url}}" alt="Album Art"
                 style="width: 200px; height: 200px; object-fit: cover; border-radius: 12px 12px 0 0; background: #222;"
                 onerror="this.onerror=null;this.src='https://via.placeholder.com/200?text=No+Image';">
            <div title="{{item['title']}}"
                 style="font-weight: 600; font-size: 1.08em; color: #fff; text-align: left; width: 100%; padding: 12px 12px 0 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{item['title']}}
            </div>
            <div title="{{item['artist']}}"
                 style="font-size: 0.98em; color: #b3b3b3; text-align: left; width: 100%; padding: 0 12px 12px 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{item['artist']}}
            </div>
        </label>
    {% endfor %}
    </div>
    <button type="submit" name="action" value="select" style="margin-top: 32px; font-size: 1.1em; padding: 10px 28px; border-radius: 8px; border: none; background: #fff; color: #18181b; font-weight: bold; cursor: pointer;">Select Album</button>
</form>
{% elif search_term %}
    <p style="color:#b3b3b3;">No albums found for <b>{{search_term}}</b>.</p>
{% endif %}

<style>
.album-card.selected-album {
    border: 2px solid #ffe066 !important;
    box-shadow: 0 0 0 2px #ffe06633;
}
</style>
<script>
document.querySelectorAll('input[type=radio][name=selected_album]').forEach(function(radio) {
    radio.addEventListener('change', function() {
        document.querySelectorAll('.album-card').forEach(function(card) {
            card.classList.remove('selected-album');
        });
        radio.closest('.album-card').classList.add('selected-album');
    });
});
document.addEventListener('DOMContentLoaded', function() {
    var checked = document.querySelector('input[type=radio][name=selected_album]:checked');
    if (checked) {
        checked.closest('.album-card').classList.add('selected-album');
    }
});
</script>
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
        <a href="https://musicbrainz.org/release/{{release['id']}}" target="_blank" style="color:#4af;">{{release['title']}}</a>
        ({{release['date'] if release.get('date') else 'Unknown Year'}}) - {{release['country'] if release.get('country') else 'Unknown Country'}}
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


TEMPLATE_LOGIN = """
<h1>Login</h1>
<form method="post">
    <input type="password" name="password" placeholder="Password" required>
    <button type="submit">Login</button>
</form>
<p style="color:red;">{{ error }}</p>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)