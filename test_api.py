#!/usr/bin/env python3
"""
Script de test pour tester les nouveaux endpoints API
"""

import requests
import json

# Test de l'endpoint tracks with_playlist_info
print("Testing /api/v1/tracks/with_playlist_info...")
try:
    response = requests.get("http://localhost:8000/api/v1/tracks/with_playlist_info?limit=3")
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Success: Got {len(data)} tracks")
        if data:
            track = data[0]
            print(f"Sample track: {track.get('title')} by {track.get('artists')}")
            if 'playlists' in track and track['playlists']:
                print(f"Playlists: {[p['playlist_name'] for p in track['playlists']]}")
            else:
                print("No playlist information")
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
except requests.exceptions.RequestException as e:
    print(f"❌ Connection error: {e}")

print("\n" + "="*50 + "\n")

# Test de l'endpoint candidates enriched
print("Testing /api/v1/candidates/enriched...")
try:
    # D'abord, obtenons une track ID
    tracks_response = requests.get("http://localhost:8000/api/v1/tracks?limit=1")
    if tracks_response.status_code == 200:
        tracks = tracks_response.json()
        if tracks:
            track_id = tracks[0]['id']
            print(f"Testing with track ID: {track_id}")
            
            response = requests.get(f"http://localhost:8000/api/v1/candidates/enriched?track_id={track_id}")
            if response.status_code == 200:
                candidates = response.json()
                print(f"✅ Success: Got {len(candidates)} candidates")
                if candidates:
                    candidate = candidates[0]
                    print(f"Sample candidate: {candidate.get('title')}")
                    if 'track' in candidate and candidate['track']:
                        track = candidate['track']
                        print(f"Track info: {track.get('title')} by {track.get('artists')}")
                        if 'playlists' in track and track['playlists']:
                            print(f"Playlists: {[p['playlist_name'] for p in track['playlists']]}")
                    else:
                        print("No track information in candidate")
            else:
                print(f"❌ Error: {response.status_code} - {response.text}")
        else:
            print("No tracks found to test candidates")
    else:
        print(f"❌ Error getting tracks: {tracks_response.status_code}")
except requests.exceptions.RequestException as e:
    print(f"❌ Connection error: {e}")