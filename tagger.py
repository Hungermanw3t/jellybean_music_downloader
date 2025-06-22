import requests
import json
import os
import time
import subprocess
import platform
import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3
from mutagen.id3 import ID3NoHeaderError
from mutagen.id3 import (
    TXXX, TPE1, TALB, TIT2, TRCK, TPOS, TDRC, APIC, TPE2, TCOM, TCON, TPUB, TMOO, TFLT, TIPL, TMCL, TSOP, TOLY,
    TSOA, # Album Artist Sort
    TSRC, # ISRC
    TDOR, # Original Release Date (ID3v2.4)
    TORY, # Original Release Year (ID3v2.3)
    TLAN, # Language
    TCOP # Copyright message
    # Removed: TDAT, TDRL, TDTG, TIAM, TOFN, TOPE, TPE3, TPE4, TPRO, TRDA, TRSN, TRSO, TSSE, TSOT, TSO2, TYER, UFID, USER, USLT, WCOM, WCOP, WOAF, WOAR, WOAS, WORS, WPAY, WPUB
)

from mutagen.m4a import M4A
from mutagen.mp4 import MP4Cover
import acoustid
from tqdm.asyncio import tqdm # Using tqdm.asyncio.tqdm for print-like output
from io import BytesIO

import config # Import config for MUSICBRAINZ_USER_AGENT, ACOUSTID_API_KEY, FPCALC_EXECUTABLE_PATH, _album_release_cache
from utils import extract_title_from_filename, log, clean_filename

def get_cover_art(release_mbid):
    """Fetches cover art from Cover Art Archive for a given MusicBrainz Release ID."""
    cover_art_url = f"https://coverartarchive.org/release/{release_mbid}/front-250.jpg" # 250px size, common for embedding
    try:
        response = requests.get(cover_art_url, headers={"User-Agent": config.MUSICBRAINZ_USER_AGENT}, timeout=5)
        response.raise_for_status()
        if response.content:
            log(f"Fetched cover art for release {release_mbid}.")
            return response.content
        return None
    except requests.exceptions.RequestException as e:
        tqdm.write(f"Warning: Could not fetch cover art for release {release_mbid}: {e}")
        return None

def tag_file_with_musicbrainz_api(
    audio_file_path,
    qobuz_album_data_for_tagging,
    track_data_for_this_file,
    acoustid_is_ready,
    fpcalc_ready_status,
    selected_mb_release_id=None  # <-- Already present
):
    log(f"\nProcessing '{os.path.basename(audio_file_path)}' with MusicBrainz API...")

    metadata = {}
    release_info_for_tagging = None
    album_artist_for_filename_parse = qobuz_album_data_for_tagging.get('artist', {}).get('name') if qobuz_album_data_for_tagging else None

    try:
        presumed_track_title_from_filename = extract_title_from_filename(os.path.basename(audio_file_path), album_artist_for_filename_parse)
        log(f"Inferred track title from filename: '{presumed_track_title_from_filename}'")

        # --- USE THE SELECTED RELEASE ID IF PROVIDED ---
        mb_release_id_for_album = None
        if selected_mb_release_id:
            mb_release_id_for_album = selected_mb_release_id
        elif qobuz_album_data_for_tagging and qobuz_album_data_for_tagging.get('id') in config._album_release_cache:
            mb_release_id_for_album = config._album_release_cache[qobuz_album_data_for_tagging['id']]

        if mb_release_id_for_album:
            log(f"Using selected MusicBrainz Release ID: {mb_release_id_for_album}")

            release_mb_url = f"https://musicbrainz.org/ws/2/release/{mb_release_id_for_album}"
            # inc parameters for Picard-like data: recordings, artists, labels, release-groups, media, isrcs (on recordings), work-rels (for original date)
            release_mb_params = {"fmt": "json", "inc": "recordings+artists+labels+release-groups+media+isrcs+work-rels"}
            release_mb_headers = {"User-Agent": config.MUSICBRAINZ_USER_AGENT}

            try:
                release_mb_response = requests.get(release_mb_url, params=release_mb_params, headers=release_mb_headers)
                release_mb_response.raise_for_status()
                release_data = release_mb_response.json()
                time.sleep(1) # Be nice to MusicBrainz API
                release_info_for_tagging = release_data
            except requests.exceptions.RequestException as e:
                tqdm.write(f"Error fetching details for selected MusicBrainz Release {mb_release_id_for_album}: {e}. Tagging may be less accurate.")
                release_info_for_tagging = None
        else:
            log("No MusicBrainz Release ID pre-selected for this Qobuz album. Attempting track-level search as primary lookup.")


        # 2. **PRIMARY LOOKUP: Match track within the selected MusicBrainz Release**
        track_info_from_mb_release = None
        if release_info_for_tagging:
            # Try to match by both title and track number (if Qobuz track data provides it)
            qobuz_track_number = track_data_for_this_file.get('track_number') if track_data_for_this_file else None

            for medium in release_info_for_tagging.get('media', []):
                for track_in_media in medium.get('tracks', []):
                    mb_track_title = track_in_media.get('title', '').strip()
                    mb_track_position = track_in_media.get('position')

                    # Prioritize exact title match and optionally track number match
                    title_matches = (mb_track_title.lower() == presumed_track_title_from_filename.lower()) or \
                                    (track_data_for_this_file and mb_track_title.lower() == track_data_for_this_file.get('title', '').lower())

                    track_number_matches = (qobuz_track_number is None) or (mb_track_position == qobuz_track_number)

                    if title_matches and track_number_matches:
                        log(f"Matched track '{presumed_track_title_from_filename}' to MusicBrainz track '{mb_track_title}' in selected release (by title and/or track number).")
                        track_info_from_mb_release = track_in_media
                        break # Found the track
                if track_info_from_mb_release:
                    break # Found the track in a medium

            if not track_info_from_mb_release:
                 log(f"Warning: Track '{presumed_track_title_from_filename}' (Qobuz Track No: {qobuz_track_number}) not found in the selected MusicBrainz release '{release_info_for_tagging.get('title')}'.")


        # 3. **FALLBACK: Use AcoustID if primary lookup failed or no album was selected**
        if not track_info_from_mb_release and acoustid_is_ready and fpcalc_ready_status:
            log("Primary lookup failed or no album selected. Attempting AcoustID match for track data.")
            mb_recording_id = None
            try:
                # AcoustID.match returns (score, recording_id, title, artist)
                acoustid_results = acoustid.match(config.ACOUSTID_API_KEY, audio_file_path)
                if acoustid_results:
                    # Sort results by score (highest first)
                    # AcoustID returns tuples, so score is first element. Recording ID is second.
                    best_match = max(acoustid_results, key=lambda x: x[0])
                    mb_recording_id = best_match[1]
                    log(f"AcoustID matched Recording ID: {mb_recording_id}")

                    # Populate AcoustID tag (the AcoustID itself, not the MBID)
                    if len(best_match) > 2 and best_match[2]: # AcoustID often includes the AcoustID itself in results
                        metadata['acoustid'] = best_match[2]


                    # Fetch MusicBrainz recording data for full details
                    recording_mb_url = f"https://musicbrainz.org/ws/2/recording/{mb_recording_id}"
                    recording_mb_params = {"fmt": "json", "inc": "releases+artists+isrcs"}
                    recording_mb_headers = {"User-Agent": config.MUSICBRAINZ_USER_AGENT}

                    recording_mb_response = requests.get(recording_mb_url, params=recording_mb_params, headers=recording_mb_headers)
                    recording_mb_response.raise_for_status()
                    recording_mb_data = recording_mb_response.json()
                    time.sleep(1) # Be nice to MusicBrainz API

                    # Populate metadata from recording data
                    metadata['musicbrainz_recordingid'] = mb_recording_id
                    if not metadata.get('title'): # Only update title if not already set from primary lookup
                        metadata['title'] = recording_mb_data.get('title')
                    if recording_mb_data.get('artist-credit'):
                        metadata['artist'] = recording_mb_data['artist-credit'][0]['name']
                        metadata['musicbrainz_artistid'] = recording_mb_data['artist-credit'][0]['artist']['id']
                        metadata['artistsort'] = recording_mb_data['artist-credit'][0]['artist'].get('sort-name') # Artist Sort Order from recording
                        # Populate multiple artists if available (Picard-like)
                        metadata['artists'] = [ac['name'] for ac in recording_mb_data['artist-credit']]

                    if 'isrcs' in recording_mb_data and recording_mb_data['isrcs']:
                        metadata['isrc'] = recording_mb_data['isrcs'][0] # Picard usually takes the first ISRC

                    # If AcoustID gave us a recording, try to find the best *release* for it
                    if 'releases' in recording_mb_data and recording_mb_data['releases']:
                        best_candidate_release = None
                        if qobuz_album_data_for_tagging and qobuz_album_data_for_tagging.get('title'):
                            qobuz_album_title_lower = qobuz_album_data_for_tagging['title'].lower()
                            for rel in recording_mb_data['releases']:
                                if rel.get('title', '').lower() == qobuz_album_title_lower and rel.get('status') == 'official':
                                    best_candidate_release = rel
                                    break

                        if not best_candidate_release:
                            # Prioritize official albums that match release group primary type 'album'
                            for rel in recording_mb_data['releases']:
                                if rel.get('status') == 'official' and rel.get('release-group', {}).get('primary-type') == 'album':
                                    best_candidate_release = rel
                                    break
                        if not best_candidate_release and recording_mb_data['releases']:
                             best_candidate_release = recording_mb_data['releases'][0] # Fallback to first if no official album found

                        if best_candidate_release:
                            log(f"Using AcoustID-derived release '{best_candidate_release.get('title')}' ({best_candidate_release.get('id')}) for album-level data.")
                            # Re-fetch full release data for the chosen AcoustID-derived release to populate album tags
                            release_mb_url = f"https://musicbrainz.org/ws/2/release/{best_candidate_release['id']}"
                            release_mb_params = {"fmt": "json", "inc": "recordings+artists+labels+release-groups+media+isrcs+work-rels"}
                            release_mb_response = requests.get(release_mb_url, params=release_mb_params, headers=release_mb_headers)
                            release_mb_response.raise_for_status()
                            release_info_for_tagging = release_mb_response.json()
                            time.sleep(1) # Be nice to MusicBrainz API

                            # Now try to find the specific track within this newly chosen release using the recording ID
                            for medium in release_info_for_tagging.get('media', []):
                                for track_in_media in medium.get('tracks', []):
                                    if track_in_media.get('recording', {}).get('id') == mb_recording_id:
                                        track_info_from_mb_release = track_in_media # Found the specific track by its recording ID
                                        break
                                if track_info_from_mb_release:
                                    break
                else:
                    log("AcoustID found no matches for this file. Basic track metadata might be limited.")
            except acoustid.AcoustidError as e:
                tqdm.write(f"AcoustID Error for '{os.path.basename(audio_file_path)}': {e}. Ensure fpcalc is in the same directory and is executable, and API key is correct. Skipping AcoustID data.")
            except FileNotFoundError:
                tqdm.write(f"Error: fpcalc not found for AcoustID. Please ensure it is in the script directory and executable, and configured in config.FPCALC_EXECUTABLE_PATH. Skipping AcoustID data.")
            except requests.exceptions.RequestException as e:
                tqdm.write(f"Error fetching MusicBrainz data after AcoustID match: {e}. Skipping AcoustID-derived data.")
            except Exception as e:
                tqdm.write(f"An unexpected error occurred during AcoustID processing: {e}")

        # 4. Populate Track-level data (from track_info_from_mb_release, if found, otherwise from Qobuz track data)
        if track_info_from_mb_release:
            metadata['title'] = track_info_from_mb_release.get('title')
            metadata['tracknumber'] = str(track_info_from_mb_release.get('position', ''))
            # Get total tracks/discs from the medium if available
            if track_info_from_mb_release.get('medium', {}).get('track-count'):
                metadata['totaltracks'] = str(track_info_from_mb_release['medium']['track-count'])
            if track_info_from_mb_release.get('medium', {}).get('position'):
                metadata['discnumber'] = str(track_info_from_mb_release['medium']['position'])
            if release_info_for_tagging and release_info_for_tagging.get('media'):
                metadata['totaldiscs'] = str(len(release_info_for_tagging['media']))

            if track_info_from_mb_release.get('artist-credit'):
                # Prioritize track-specific artist if present
                metadata['artist'] = track_info_from_mb_release['artist-credit'][0]['name']
                metadata['musicbrainz_artistid'] = track_info_from_mb_release['artist-credit'][0]['artist']['id']
                metadata['artistsort'] = track_info_from_mb_release['artist-credit'][0]['artist'].get('sort-name')
                metadata['artists'] = [ac['name'] for ac in track_info_from_mb_release['artist-credit']]
            elif track_data_for_this_file and track_data_for_this_file.get('artist'): # Fallback to Qobuz track artist
                metadata['artist'] = track_data_for_this_file.get('artist')


            if track_info_from_mb_release.get('recording', {}).get('id'):
                metadata['musicbrainz_recordingid'] = track_info_from_mb_release['recording']['id']
                isrcs = track_info_from_mb_release['recording'].get('isrcs', [])
                if isrcs:
                    metadata['isrc'] = isrcs[0]

            metadata['musicbrainz_trackid'] = track_info_from_mb_release.get('id') # MB Track ID (track on release)
        elif track_data_for_this_file: # Fallback to Qobuz track data for basic info if no MB track match found
            tqdm.write("Using Qobuz track data for basic metadata as MusicBrainz track match failed.")
            metadata['title'] = track_data_for_this_file.get('title')
            metadata['artist'] = track_data_for_this_file.get('artist')
            metadata['tracknumber'] = str(track_data_for_this_file.get('track_number', ''))
            # Total tracks/discs are harder to get accurately from single Qobuz track API call

        if not metadata.get('title'):
             metadata['title'] = presumed_track_title_from_filename # Last resort for title

        # 5. Populate Album-level data (from release_info_for_tagging, if available)
        if release_info_for_tagging:
            metadata['album'] = release_info_for_tagging.get('title')
            metadata['musicbrainz_releaseid'] = release_info_for_tagging.get('id')

            if release_info_for_tagging.get('release-group') and release_info_for_tagging['release-group'].get('id'):
                metadata['musicbrainz_releasegroupid'] = release_info_for_tagging['release-group']['id']
                if release_info_for_tagging['release-group'].get('primary-type'):
                    metadata['releasetype'] = release_info_for_tagging['release-group']['primary-type']
                if release_info_for_tagging['release-group'].get('secondary-types'):
                    metadata['releasetype_secondary'] = "; ".join(release_info_for_tagging['release-group']['secondary-types'])


                if release_info_for_tagging['release-group'].get('first-release-date'):
                    metadata['original_release_date'] = release_info_for_tagging['release-group']['first-release-date']
                    metadata['original_year'] = release_info_for_tagging['release-group']['first-release-date'].split('-')[0]

            # Use the "date" field for the primary date tag (Picard typically uses the release date)
            # Prioritize a full date if available, otherwise fallback to original_release_date or just year
            if release_info_for_tagging.get('date'):
                metadata['date'] = release_info_for_tagging['date']
                metadata['year'] = release_info_for_tagging['date'].split('-')[0]
            elif 'original_release_date' in metadata: # Fallback if 'date' is not present but original is
                metadata['date'] = metadata['original_release_date']
                metadata['year'] = metadata['original_release_date'].split('-')[0]


            if release_info_for_tagging.get('artist-credit'):
                metadata['albumartist'] = release_info_for_tagging['artist-credit'][0]['name']
                metadata['musicbrainz_albumartistid'] = release_info_for_tagging['artist-credit'][0]['artist']['id']
                metadata['albumartistsort'] = release_info_for_tagging['artist-credit'][0]['artist'].get('sort-name')

            if release_info_for_tagging.get('label-info'):
                label_info = release_info_for_tagging['label-info'][0]
                if label_info.get('label', {}).get('name'):
                    metadata['label'] = label_info['label']['name']
                if label_info.get('catalog-number'):
                    metadata['catalognumber'] = label_info['catalog-number']
            if release_info_for_tagging.get('barcode'):
                metadata['barcode'] = release_info_for_tagging['barcode']
            if release_info_for_tagging.get('country'):
                metadata['country'] = release_info_for_tagging.get('country')
            if release_info_for_tagging.get('status'):
                metadata['status'] = release_info_for_tagging.get('status')
            if release_info_for_tagging.get('media'): # Take format from first medium
                metadata['media_format'] = release_info_for_tagging['media'][0].get('format')
            if release_info_for_tagging.get('text-representation', {}).get('language'):
                metadata['language'] = release_info_for_tagging['text-representation']['language']
            if release_info_for_tagging.get('text-representation', {}).get('script'):
                metadata['script'] = release_info_for_tagging['text-representation']['script']
            if release_info_for_tagging.get('copyright'): # General copyright
                metadata['copyright'] = release_info_for_tagging['copyright']

        elif qobuz_album_data_for_tagging: # Fallback to Qobuz album data if no MB release was found
            tqdm.write("Using Qobuz album data for basic album-level metadata.")
            metadata['album'] = qobuz_album_data_for_tagging.get('title')
            metadata['albumartist'] = qobuz_album_data_for_tagging.get('artist', {}).get('name')
            metadata['year'] = qobuz_album_data_for_tagging.get('release_date', '').split('-')[0]
            metadata['date'] = qobuz_album_data_for_tagging.get('release_date', '') # Use full Qobuz release date


        log(f"Collected MusicBrainz metadata for '{os.path.basename(audio_file_path)}':")
        for key, value in metadata.items():
            if value is not None and value != '':
                log(f"  {key}: {value}")


        # 6. Fetch Cover Art (always from the selected/inferred album release)
        cover_art_data = None
        if 'musicbrainz_releaseid' in metadata and metadata['musicbrainz_releaseid']:
            cover_art_data = get_cover_art(metadata['musicbrainz_releaseid'])


        # 7. Write tags to file using Mutagen
        file_extension = os.path.splitext(audio_file_path)[1].lower()
        audio = None

        if file_extension == '.flac':
            try:
                audio = FLAC(audio_file_path)
            except mutagen.flac.FLACNoHeaderError:
                tqdm.write(f"Error: Not a valid FLAC file '{audio_file_path}'. Skipping tagging.")
                return False

            audio.clear() # Clear all existing Vorbis comments to mimic clean slate

            # Basic tags
            if 'title' in metadata: audio['TITLE'] = str(metadata['title'])
            if 'artist' in metadata: audio['ARTIST'] = str(metadata['artist'])
            if 'album' in metadata: audio['ALBUM'] = str(metadata['album'])
            if 'albumartist' in metadata: audio['ALBUMARTIST'] = str(metadata['albumartist'])
            if 'date' in metadata: audio['DATE'] = str(metadata['date']) # Use full date for FLAC
            if 'artists' in metadata: audio['ARTISTS'] = metadata['artists'] # Picard writes multiple ARTISTS for FLAC

            # Sort Order tags
            if 'albumartistsort' in metadata and metadata['albumartistsort']: audio['ALBUMARTISTSORT'] = str(metadata['albumartistsort'])
            if 'artistsort' in metadata and metadata['artistsort']: audio['ARTISTSORT'] = str(metadata['artistsort'])

            # Track and Disc numbers (Picard style for FLAC - separate total fields)
            if 'tracknumber' in metadata and metadata['tracknumber']: audio['TRACKNUMBER'] = str(metadata['tracknumber'])
            if 'totaltracks' in metadata and metadata['totaltracks']: audio['TRACKTOTAL'] = str(metadata['totaltracks'])
            if 'discnumber' in metadata and metadata['discnumber']: audio['DISCNUMBER'] = str(metadata['discnumber'])
            if 'totaldiscs' in metadata and metadata['totaldiscs']: audio['DISCTOTAL'] = str(metadata['totaldiscs'])

            # MusicBrainz IDs (Picard style Vorbis comments)
            if 'musicbrainz_recordingid' in metadata: audio['MUSICBRAINZ_RECORDINGID'] = str(metadata['musicbrainz_recordingid'])
            if 'musicbrainz_artistid' in metadata: audio['MUSICBRAINZ_ARTISTID'] = str(metadata['musicbrainz_artistid'])
            if 'musicbrainz_albumartistid' in metadata: audio['MUSICBRAINZ_ALBUMARTISTID'] = str(metadata['musicbrainz_albumartistid'])
            if 'musicbrainz_releaseid' in metadata: audio['MUSICBRAINZ_RELEASEID'] = str(metadata['musicbrainz_releaseid'])
            if 'musicbrainz_releasegroupid' in metadata: audio['MUSICBRAINZ_RELEASEGROUPID'] = str(metadata['musicbrainz_releasegroupid'])
            if 'musicbrainz_trackid' in metadata: audio['MUSICBRAINZ_TRACKID'] = str(metadata['musicbrainz_trackid']) # MB Track ID (not recording ID)
            if 'acoustid' in metadata: audio['ACOUSTID_ID'] = str(metadata['acoustid']) # Add AcoustID

            # Other Picard tags
            if 'isrc' in metadata: audio['ISRC'] = str(metadata['isrc'])
            if 'barcode' in metadata: audio['BARCODE'] = str(metadata['barcode'])
            if 'catalognumber' in metadata: audio['CATALOGNUMBER'] = str(metadata['catalognumber'])
            if 'original_release_date' in metadata: audio['ORIGINALDATE'] = str(metadata['original_release_date'])
            if 'original_year' in metadata: audio['ORIGINALYEAR'] = str(metadata['original_year']) # From release group
            if 'label' in metadata: audio['LABEL'] = str(metadata['label'])
            if 'country' in metadata: audio['MUSICBRAINZ_RELEASE_COUNTRY'] = str(metadata['country']) # Specific Picard field for country
            if 'status' in metadata: audio['MUSICBRAINZ_RELEASE_STATUS'] = str(metadata['status']) # Specific Picard field for status
            if 'media_format' in metadata: audio['MEDIA'] = str(metadata['media_format'])
            if 'releasetype' in metadata: audio['RELEASETYPE'] = str(metadata['releasetype']) # Also for 'primary-type' of release group
            if 'releasetype_secondary' in metadata: audio['RELEASETYPE_SECONDARY'] = str(metadata['releasetype_secondary']) # Also for 'secondary-types' of release group
            if 'language' in metadata: audio['LANGUAGE'] = str(metadata['language'])
            if 'script' in metadata: audio['SCRIPT'] = str(metadata['script'])
            if 'copyright' in metadata: audio['COPYRIGHT'] = str(metadata['copyright'])


            if cover_art_data:
                image = Picture()
                image.data = cover_art_data
                image.type = mutagen.id3.PictureType.COVER_FRONT # 3 is Front Cover
                image.mime = 'image/jpeg'
                audio.add_picture(image)

        elif file_extension == '.mp3':
            try:
                audio = MP3(audio_file_path)
            except ID3NoHeaderError: # If no ID3 header exists, create a new one
                audio = MP3(audio_file_path)
                audio.add_tags() # Add ID3 tags if they don't exist

            audio.clear() # Clear all existing ID3 tags to mimic clean slate

            # Standard tags
            if 'title' in metadata: audio['TIT2'] = TIT2(encoding=3, text=[metadata['title']])
            if 'artist' in metadata: audio['TPE1'] = TPE1(encoding=3, text=[metadata['artist']])
            if 'albumartist' in metadata: audio['TPE2'] = TPE2(encoding=3, text=[metadata['albumartist']]) # Album Artist
            if 'album' in metadata: audio['TALB'] = TALB(encoding=3, text=[metadata['album']])
            if 'date' in metadata: audio['TDRC'] = TDRC(encoding=3, text=[metadata['date']]) # TDRC for date (ID3v2.4)
            # If multiple artists, Picard usually uses TPE1 for the first artist and adds TXXX:ARTISTS for others
            if 'artists' in metadata and len(metadata['artists']) > 1:
                # Store all artists in a TXXX frame like Picard often does
                audio['TXXX:ARTISTS'] = TXXX(encoding=3, desc='ARTISTS', text=["; ".join(metadata['artists'])]) # Picard uses semicolon separated
            elif 'artists' in metadata and len(metadata['artists']) == 1:
                audio['TPE1'] = TPE1(encoding=3, text=[metadata['artists'][0]]) # Just primary artist


            # Sort Order tags (TSOA for Album Artist Sort, TSOP for Artist Sort/Performer Sort)
            if 'albumartistsort' in metadata and metadata['albumartistsort']: audio['TSOA'] = TSOA(encoding=3, text=[metadata['albumartistsort']])
            if 'artistsort' in metadata and metadata['artistsort']: audio['TSOP'] = TSOP(encoding=3, text=[metadata['artistsort']])


            # Track and Disc numbers (Picard style for MP3 - XX/YY)
            if 'tracknumber' in metadata and metadata['tracknumber']:
                total_tracks_str = str(metadata.get('totaltracks', ''))
                audio['TRCK'] = TRCK(encoding=3, text=[f"{metadata['tracknumber']}/{total_tracks_str}".rstrip('/')])
            if 'discnumber' in metadata and metadata['discnumber']:
                total_discs_str = str(metadata.get('totaldiscs', ''))
                audio['TPOS'] = TPOS(encoding=3, text=[f"{metadata['discnumber']}/{total_discs_str}".rstrip('/')])

            # MusicBrainz IDs (Picard style TXXX frames)
            if 'musicbrainz_recordingid' in metadata: audio['TXXX:MusicBrainz Recording Id'] = TXXX(encoding=3, desc='MusicBrainz Recording Id', text=[metadata['musicbrainz_recordingid']])
            if 'musicbrainz_artistid' in metadata: audio['TXXX:MusicBrainz Artist Id'] = TXXX(encoding=3, desc='MusicBrainz Artist Id', text=[metadata['musicbrainz_artistid']])
            if 'musicbrainz_albumartistid' in metadata: audio['TXXX:MusicBrainz Album Artist Id'] = TXXX(encoding=3, desc='MusicBrainz Album Artist Id', text=[metadata['musicbrainz_albumartistid']])
            if 'musicbrainz_releaseid' in metadata: audio['TXXX:MusicBrainz Album Id'] = TXXX(encoding=3, desc='MusicBrainz Album Id', text=[metadata['musicbrainz_releaseid']]) # Picard uses Album Id for Release Id
            if 'musicbrainz_releasegroupid' in metadata: audio['TXXX:MusicBrainz Release Group Id'] = TXXX(encoding=3, desc='MusicBrainz Release Group Id', text=[metadata['musicbrainz_releasegroupid']])
            if 'musicbrainz_trackid' in metadata: audio['TXXX:MusicBrainz Track Id'] = TXXX(encoding=3, desc='MusicBrainz Track Id', text=[metadata['musicbrainz_trackid']]) # For track-on-release ID
            if 'acoustid' in metadata: audio['TXXX:Acoustid Id'] = TXXX(encoding=3, desc='Acoustid Id', text=[metadata['acoustid']]) # Add AcoustID

            # Other Picard tags
            if 'isrc' in metadata: audio['TSRC'] = TSRC(encoding=3, text=[metadata['isrc']]) # Standard ISRC frame
            if 'barcode' in metadata: audio['TXXX:BARCODE'] = TXXX(encoding=3, desc='BARCODE', text=[metadata['barcode']])
            if 'catalognumber' in metadata: audio['TXXX:CATALOGNUMBER'] = TXXX(encoding=3, desc='CATALOGNUMBER', text=[metadata['catalognumber']])
            if 'original_release_date' in metadata: audio['TDOR'] = TDOR(encoding=3, text=[metadata['original_release_date']]) # Original Release Date (ID3v2.4)
            if 'original_year' in metadata: audio['TORY'] = TORY(encoding=3, text=[metadata['original_year']]) # Original Release Year (ID3v2.3)
            if 'label' in metadata: audio['TPUB'] = TPUB(encoding=3, text=[metadata['label']]) # Publisher/Label
            if 'country' in metadata: audio['TXXX:MusicBrainz Album Release Country'] = TXXX(encoding=3, desc='MusicBrainz Album Release Country', text=[metadata['country']])
            if 'status' in metadata: audio['TXXX:MusicBrainz Album Status'] = TXXX(encoding=3, desc='MusicBrainz Album Status', text=[metadata['status']])
            if 'media_format' in metadata: audio['TXXX:MEDIA'] = TXXX(encoding=3, desc='MEDIA', text=[metadata['media_format']])
            if 'releasetype' in metadata: audio['TXXX:RELEASETYPE'] = TXXX(encoding=3, desc='RELEASETYPE', text=[metadata['releasetype']])
            if 'releasetype_secondary' in metadata: audio['TXXX:RELEASETYPE_SECONDARY'] = TXXX(encoding=3, desc='RELEASETYPE_SECONDARY', text=[metadata['releasetype_secondary']])
            if 'language' in metadata: audio['TLAN'] = TLAN(encoding=3, text=[metadata['language']]) # Language
            if 'script' in metadata: audio['TXXX:SCRIPT'] = TXXX(encoding=3, desc='SCRIPT', text=[metadata['script']])
            if 'copyright' in metadata: audio['TCOP'] = TCOP(encoding=3, text=[metadata['copyright']])


            if cover_art_data:
                image = APIC(
                    encoding=3, # UTF-8
                    mime='image/jpeg',
                    type=3, # 3 is Front Cover
                    desc='Front Cover',
                    data=cover_art_data
                )
                audio.add(image)

        elif file_extension == '.m4a':
            try:
                audio = M4A(audio_file_path)
            except Exception as e: # M4A can throw various errors on bad files
                tqdm.write(f"Error: Not a valid M4A file '{audio_file_path}' or error opening. Skipping tagging: {e}.")
                return False

            audio.clear() # Clear all existing atoms

            # Standard tags
            if 'title' in metadata: audio['\xa9nam'] = metadata['title']
            if 'artist' in metadata: audio['\xa9ART'] = metadata['artist']
            if 'albumartist' in metadata: audio['aART'] = metadata['albumartist'] # Album Artist
            if 'album' in metadata: audio['\xa9alb'] = metadata['album']
            if 'date' in metadata: audio['\xa9day'] = metadata['date'] # Year for M4A, but Picard can store full date here
            if 'artists' in metadata and len(metadata['artists']) > 1:
                audio['----:com.apple.iTunes:ARTISTS'] = "; ".join(metadata['artists']).encode('utf-8')
            elif 'artists' in metadata and len(metadata['artists']) == 1:
                audio['\xa9ART'] = metadata['artists'][0] # Just primary artist

            # Sort Order tags (M4A standard atom names for sort order)
            if 'albumartistsort' in metadata and metadata['albumartistsort']: audio['soaa'] = metadata['albumartistsort']
            if 'artistsort' in metadata and metadata['artistsort']: audio['soar'] = metadata['artistsort']

            # Track and Disc numbers (Picard style for M4A - tuple)
            if 'tracknumber' in metadata and metadata['tracknumber']:
                total_tracks_int = int(metadata.get('totaltracks', 0)) if metadata.get('totaltracks') else 0
                audio['trkn'] = [(int(metadata['tracknumber']), total_tracks_int)]
            if 'discnumber' in metadata and metadata['discnumber']:
                total_discs_int = int(metadata.get('totaldiscs', 0)) if metadata.get('totaldiscs') else 0
                audio['disk'] = [(int(metadata['discnumber']), total_discs_int)]

            # MusicBrainz IDs (Picard style custom iTunes atoms)
            if 'musicbrainz_recordingid' in metadata: audio['----:com.apple.iTunes:MusicBrainz Recording Id'] = metadata['musicbrainz_recordingid'].encode('utf-8')
            if 'musicbrainz_artistid' in metadata: audio['----:com.apple.iTunes:MusicBrainz Artist Id'] = metadata['musicbrainz_artistid'].encode('utf-8')
            if 'musicbrainz_albumartistid' in metadata: audio['----:com.apple.iTunes:MusicBrainz Album Artist Id'] = metadata['musicbrainz_albumartistid'].encode('utf-8')
            if 'musicbrainz_releaseid' in metadata: audio['----:com.apple.iTunes:MusicBrainz Album Id'] = metadata['musicbrainz_releaseid'].encode('utf-8') # Picard uses Album Id for Release Id
            if 'musicbrainz_releasegroupid' in metadata: audio['----:com.apple.iTunes:MusicBrainz Release Group Id'] = metadata['musicbrainz_releasegroupid'].encode('utf-8')
            if 'musicbrainz_trackid' in metadata: audio['----:com.apple.iTunes:MusicBrainz Track Id'] = metadata['musicbrainz_trackid'].encode('utf-8')
            if 'acoustid' in metadata: audio['----:com.apple.iTunes:Acoustid Id'] = metadata['acoustid'].encode('utf-8') # Add AcoustID

            # Other Picard tags
            if 'isrc' in metadata: audio['----:com.apple.iTunes:ISRC'] = metadata['isrc'].encode('utf-8')
            if 'barcode' in metadata: audio['----:com.apple.iTunes:BARCODE'] = metadata['barcode'].encode('utf-8')
            if 'catalognumber' in metadata: audio['----:com.apple.iTunes:CATALOGNUMBER'] = metadata['catalognumber'].encode('utf-8')
            if 'original_release_date' in metadata: audio['----:com.apple.iTunes:ORIGINAL RELEASE DATE'] = metadata['original_release_date'].encode('utf-8')
            if 'original_year' in metadata: audio['----:com.apple.iTunes:ORIGINAL YEAR'] = metadata['original_year'].encode('utf-8')
            if 'label' in metadata: audio['\xa9lab'] = metadata['label'] # Publisher/Label (standard for M4A)
            if 'country' in metadata: audio['----:com.apple.iTunes:MusicBrainz Album Release Country'] = metadata['country'].encode('utf-8')
            if 'status' in metadata: audio['----:com.apple.iTunes:MusicBrainz Album Status'] = metadata['status'].encode('utf-8')
            if 'media_format' in metadata: audio['----:com.apple.iTunes:MEDIA'] = metadata['media_format'].encode('utf-8')
            if 'releasetype' in metadata: audio['----:com.apple.iTunes:RELEASETYPE'] = metadata['releasetype'].encode('utf-8')
            if 'releasetype_secondary' in metadata: audio['----:com.apple.iTunes:RELEASETYPE_SECONDARY'] = metadata['releasetype_secondary'].encode('utf-8')
            if 'language' in metadata: audio['----:com.apple.iTunes:LANGUAGE'] = metadata['language'].encode('utf-8')
            if 'script' in metadata: audio['----:com.apple.iTunes:SCRIPT'] = metadata['script'].encode('utf-8')
            if 'copyright' in metadata: audio['----:com.apple.iTunes:COPYRIGHT'] = metadata['copyright'].encode('utf-8')


            if cover_art_data:
                cover = MP4Cover(cover_art_data, imageformat=MP4Cover.FORMAT_JPEG)
                audio['covr'] = [cover]

        if audio:
            audio.save()
            log(f"Successfully tagged '{os.path.basename(audio_file_path)}' with Picard-like MusicBrainz data.")
            return True
        else:
            tqdm.write(f"Unsupported file format for tagging: '{audio_file_path}'.")
            return False

    except requests.exceptions.RequestException as e:
        tqdm.write(f"MusicBrainz API Error for '{os.path.basename(audio_file_path)}': {e}")
        return False
    except mutagen.MutagenError as e:
        tqdm.write(f"Error writing tags to '{os.path.basename(audio_file_path)}': {e}")
        return False
    except Exception as e:
        tqdm.write(f"An unexpected error occurred during tagging of '{os.path.basename(audio_file_path)}': {e}")
        return False

# Function to check fpcalc presence and executability
def check_fpcalc_readiness():
    fpcalc_is_present_and_executable = False
    if os.path.exists(config.FPCALC_EXECUTABLE_PATH):
        try:
            # Attempt to run it to ensure it's executable using the correct '-version' flag
            subprocess.run([config.FPCALC_EXECUTABLE_PATH, "-version"], capture_output=True, check=True, text=True, timeout=5)
            log(f"fpcalc executable found and is runnable at: '{config.FPCALC_EXECUTABLE_PATH}'.")
            fpcalc_is_present_and_executable = True
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
            log(f"WARNING: fpcalc found at '{config.FPCALC_EXECUTABLE_PATH}' but could not be executed: {e}")
            log("This could be due to permissions, a corrupted file, or missing system dependencies for fpcalc itself.")
            log("AcoustID fallback for MusicBrainz tagging will be skipped due to fpcalc issue.")
    else:
        log(f"WARNING: fpcalc not found at '{config.FPCALC_EXECUTABLE_PATH}'. AcoustID fallback for MusicBrainz tagging will be skipped.")
    return fpcalc_is_present_and_executable

import asyncio
import time

class MusicBrainzRateLimiter:
    def __init__(self, min_interval=1.0):
        self.min_interval = min_interval
        self._last_call = 0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_call = time.monotonic()

async def tag_file_worker(
    file_ready_queue,
    qobuz_album_data_for_tagging,
    items_to_download,
    acoustid_is_ready,
    fpcalc_ready_status,
    rate_limiter,
    tag_progress=None
):
    while True:
        file_info = await file_ready_queue.get()
        if file_info is None:
            break
        audio_file_path, download_format = file_info
        filename_only = os.path.basename(audio_file_path)
        track_data_for_this_file = None
        for q_track_data in items_to_download:
            expected_filename = f"{clean_filename(q_track_data['artist'])} - {clean_filename(q_track_data['title'])}.{download_format.lower()}"
            if expected_filename == filename_only:
                track_data_for_this_file = q_track_data
                break
        # Wait for MusicBrainz rate limit
        await rate_limiter.wait()
        # Tag the file (run in thread to avoid blocking event loop)
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
        if tag_progress:
            tag_progress.update(1)
        file_ready_queue.task_done()
        yield  # This makes it an async generator