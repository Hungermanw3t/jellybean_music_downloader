from qobuz_api import get_music_info, get_album_details

# Test search
results = get_music_info('Brasilian Skies', music_type='albums', limit=3)
print('Search Results:')
if results:
    for i, result in enumerate(results):
        print(f'{i}: {result}')
        print()
    
    # Test getting album details for first result
    album_id = results[0]['id']
    print(f'\nGetting details for album ID: {album_id}')
    album_data, tracks = get_album_details(album_id)
    print(f'Album data keys: {album_data.keys() if album_data else None}')
    print(f'Album data: {album_data}')
    if tracks:
        print(f'First track: {tracks[0]}')
else:
    print('No search results found')
