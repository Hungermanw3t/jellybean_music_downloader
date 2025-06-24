"""
Automatic release matching for better MusicBrainz tagging
"""
import musicbrainzngs
from difflib import SequenceMatcher
import re
from datetime import datetime

class ReleaseMatcher:
    def __init__(self):
        musicbrainzngs.set_useragent("QobuzSquidDownloader", "1.0", "your@email.com")
    
    def clean_string(self, text):
        """Clean string for better matching"""
        if not text:
            return ""
        # Remove special characters, normalize spaces
        text = re.sub(r'[^\w\s]', '', text.lower())
        text = re.sub(r'\s+', ' ', text).strip()
        return text
    
    def similarity_score(self, str1, str2):
        """Calculate similarity between two strings"""
        return SequenceMatcher(None, self.clean_string(str1), self.clean_string(str2)).ratio()
    
    def find_best_release(self, artist, album, track_count=None, release_year=None):
        """
        Automatically find the best MusicBrainz release match
        """
        try:
            # Search for releases
            result = musicbrainzngs.search_releases(
                artist=artist, 
                release=album, 
                limit=20
            )
            
            releases = result.get("release-list", [])
            if not releases:
                return None
            
            best_release = None
            best_score = 0
            
            for release in releases:
                score = 0
                
                # Artist name matching (highest weight)
                artist_credits = release.get('artist-credit', [])
                if artist_credits:
                    release_artist = artist_credits[0].get('artist', {}).get('name', '')
                    artist_similarity = self.similarity_score(artist, release_artist)
                    score += artist_similarity * 40
                
                # Album title matching (high weight)
                release_title = release.get('title', '')
                title_similarity = self.similarity_score(album, release_title)
                score += title_similarity * 35
                
                # Prefer official releases (medium weight)
                release_group = release.get('release-group', {})
                primary_type = release_group.get('primary-type', '')
                if primary_type.lower() == 'album':
                    score += 10
                
                # Prefer releases with cover art (small weight)
                if release.get('cover-art-archive', {}).get('front', False):
                    score += 5
                
                # Track count matching (if available)
                if track_count:
                    try:
                        # Get detailed release info
                        detailed = musicbrainzngs.get_release_by_id(
                            release['id'], 
                            includes=['recordings']
                        )
                        release_track_count = len(
                            detailed['release'].get('medium-list', [{}])[0].get('track-list', [])
                        )
                        if release_track_count == track_count:
                            score += 8
                        elif abs(release_track_count - track_count) <= 2:
                            score += 4
                    except:
                        pass
                
                # Release year matching (if available)
                if release_year:
                    release_date = release.get('date', '')
                    if release_date and len(release_date) >= 4:
                        try:
                            rel_year = int(release_date[:4])
                            if rel_year == release_year:
                                score += 8
                            elif abs(rel_year - release_year) <= 1:
                                score += 4
                        except:
                            pass
                
                # Prefer earlier/original releases
                status = release.get('status', '')
                if status.lower() == 'official':
                    score += 3
                
                if score > best_score:
                    best_score = score
                    best_release = release
            
            # Only return if we have a reasonable match (>60% confidence)
            if best_score > 60:
                return {
                    'id': best_release['id'],
                    'title': best_release.get('title', ''),
                    'artist': best_release.get('artist-credit', [{}])[0].get('artist', {}).get('name', ''),
                    'score': best_score,
                    'confidence': 'high' if best_score > 80 else 'medium'
                }
            
            return None
            
        except Exception as e:
            print(f"Error finding best release: {e}")
            return None
    
    def get_qobuz_metadata(self, album_data):
        """Extract useful metadata from Qobuz album data"""
        return {
            'track_count': len(album_data.get('tracks', {}).get('items', [])),
            'release_year': album_data.get('released_at', None),
            'label': album_data.get('label', {}).get('name', ''),
            'genre': album_data.get('genre', {}).get('name', '')
        }
