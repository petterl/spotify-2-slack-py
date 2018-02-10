import os
from datetime import datetime

import spotipy
import spotipy.util
from slackclient import SlackClient
import redis

DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ" # 2016-12-21T12:32:21Z

def updated_tracks(playlist_name, playlist_href, tracks, since):
    global lastDate
    msg = 'New tracks in playlist <{1}|{0}> since {2}\n'.format(playlist_name, playlist_href, since)
    for i, item in enumerate(tracks):
        artist = item['track']['artists'][0]['name']
        href = item['track']['external_urls']['spotify'] if item['track']['external_urls'] else item['track']['external_urls']
        song = item['track']['name']
        user = item['added_by']['id'] if item['added_by'] else 'Unknown'
        user_href = 'https://open.spotify.com/user/{}'.format(user)
        date = datetime.strptime(item['added_at'], DATE_FORMAT)
        lastDate = date if date >= lastDate else lastDate
        msg += '    {0} - *<{3}|{1}>* added by <{4}|{2}>\n'.format(artist, song, user, href, user_href)
    return msg

def get_playlist_tracks(playlist_username, playlist_id):
    results = spotify.user_playlist(playlist_username, playlist_id, fields="name,external_urls,tracks,next")
    href = results['external_urls']['spotify']
    name = results['name']
    tracks = results['tracks'].copy()
    items = tracks['items']
    while tracks['next']:
        tracks = spotify.next(tracks)
        items += tracks['items']
    return (name, href, items)

def init_spotipy(username, client_id, client_secret, cache_data):
    cache_filename = './.cache-{}'.format(username)
    f = open(cache_filename,"w+")
    f.write(cache_data) 
    f.close()
    token = spotipy.util.prompt_for_user_token(
        username,        
        'playlist-read-private',
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri='http://localhost/')
    return spotipy.Spotify(auth=token)

if __name__ == '__main__':
    if(os.getenv('REDISTOGO_URL')):
        redis = redis.from_url(os.getenv('REDISTOGO_URL'))
    else:
        redis = redis.StrictRedis(host='localhost', port=6379, db=0)

    spotify = init_spotipy(
        os.environ['SPOTIFY_USERNAME'],
        os.environ['SPOTIFY_CLIENT_ID'],
        os.environ['SPOTIFY_CLIENT_SECRET'],
        os.environ['SPOTIPY_CACHE'])

    #redis.delete('lastDate')
    lastDate = redis.get('lastDate')

    if lastDate is None:
    #    print("No lastDate found in redis, setting to min")
        lastDate = datetime.min
    else:
        lastDate = datetime.strptime(lastDate.decode('UTF-8'), DATE_FORMAT)
    #    print("Date of prev fetch was: {}".format(lastDate))

    slack_token = os.environ["SLACK_API_TOKEN"]
    slack = SlackClient(slack_token)

    playlist_ids=os.environ['SPOTIFY_PLAYLIST_IDS'].split(',')
    playlist_username = os.getenv('SPOTIFY_PLAYLIST_USERNAME', os.environ['SPOTIFY_USERNAME'])
    for playlist_id in playlist_ids:
        (name, href, items) = get_playlist_tracks(playlist_username, playlist_id)
        items = [a for a in items if datetime.strptime(a['added_at'], DATE_FORMAT) > lastDate]
        if len(items) > 0:
            msg = updated_tracks(name, href, items, lastDate)
            slack.api_call(
                "chat.postMessage",
                channel="@psa",
                text=msg
            )

    redis.set('lastDate', lastDate.strftime(DATE_FORMAT))

