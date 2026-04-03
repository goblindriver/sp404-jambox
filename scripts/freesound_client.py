#!/usr/bin/env python3
"""
Freesound.org API v2 client with OAuth2 support.
- Token auth: search + preview downloads
- OAuth2 auth: full quality original file downloads

OAuth2 flow: browser opens → user authorizes → pastes code → token saved to .env
"""
import os, json, webbrowser, requests
from urllib.parse import urlencode

API_BASE = "https://freesound.org/apiv2"
AUTH_URL = "https://freesound.org/apiv2/oauth2/authorize/"
TOKEN_URL = "https://freesound.org/apiv2/oauth2/access_token/"
REQUEST_TIMEOUT = 30

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
ENV_PATH = os.path.join(REPO_DIR, ".env")


def _load_env():
    """Load key=value pairs from .env file."""
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    return env


def _save_env(env):
    """Write key=value pairs back to .env file."""
    with open(ENV_PATH, 'w') as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")


def _get_api_key():
    env = _load_env()
    key = env.get('FREESOUND_API_KEY')
    if not key:
        raise RuntimeError("No FREESOUND_API_KEY in .env")
    return key


def _get_oauth_token():
    """Get OAuth2 access token if available."""
    env = _load_env()
    return env.get('FREESOUND_OAUTH_TOKEN')


def _get_client_id():
    env = _load_env()
    return env.get('FREESOUND_CLIENT_ID')


def _get_client_secret():
    env = _load_env()
    return env.get('FREESOUND_CLIENT_SECRET')


def setup_oauth():
    """Interactive OAuth2 setup. Opens browser for user authorization."""
    client_id = _get_client_id()
    if not client_id:
        print("OAuth2 requires FREESOUND_CLIENT_ID and FREESOUND_CLIENT_SECRET in .env")
        print("Register your app at: https://freesound.org/apiv2/apply/")
        print("Then add to .env:")
        print("  FREESOUND_CLIENT_ID=your_client_id")
        print("  FREESOUND_CLIENT_SECRET=your_client_secret")
        return False

    client_secret = _get_client_secret()
    if not client_secret:
        print("Missing FREESOUND_CLIENT_SECRET in .env")
        return False

    # Open browser for authorization
    auth_params = urlencode({
        'client_id': client_id,
        'response_type': 'code',
        'state': 'sp404jambox',
    })
    auth_url = f"{AUTH_URL}?{auth_params}"
    print(f"Opening browser for Freesound authorization...")
    print(f"If it doesn't open, visit: {auth_url}")
    webbrowser.open(auth_url)

    # Get code from user
    code = input("\nPaste the authorization code here: ").strip()
    if not code:
        print("No code provided, aborting.")
        return False

    # Exchange code for token
    try:
        resp = requests.post(TOKEN_URL, data={
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'authorization_code',
            'code': code,
        }, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        print(f"Token exchange failed: {exc}")
        return False

    if resp.status_code != 200:
        print(f"Token exchange failed: {resp.status_code} {resp.text}")
        return False

    try:
        token_data = resp.json()
    except ValueError:
        print("Token exchange failed: invalid JSON response")
        return False
    access_token = token_data.get('access_token')
    if not access_token:
        print("Token exchange failed: response did not include access_token")
        return False
    env = _load_env()
    env['FREESOUND_OAUTH_TOKEN'] = access_token
    if 'refresh_token' in token_data:
        env['FREESOUND_OAUTH_REFRESH'] = token_data['refresh_token']
    _save_env(env)
    print("OAuth2 token saved to .env")
    return True


def search(query, duration_min=0.1, duration_max=30, page_size=5):
    """Search Freesound for sounds matching a query.

    Returns list of dicts with: id, name, duration, tags, license, previews, username
    """
    api_key = _get_api_key()
    params = {
        'query': query,
        'filter': f'duration:[{duration_min} TO {duration_max}]',
        'fields': 'id,name,duration,tags,license,previews,username,samplerate,channels',
        'page_size': page_size,
        'sort': 'score',
        'token': api_key,
    }
    try:
        resp = requests.get(f"{API_BASE}/search/text/", params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        print(f"  Search failed: {exc}")
        return []
    if resp.status_code != 200:
        print(f"  Search failed: {resp.status_code}")
        return []

    try:
        data = resp.json()
    except ValueError:
        print("  Search failed: invalid JSON response")
        return []
    return data.get('results', [])


def download(sound_id, dest_path):
    """Download a sound file. Tries OAuth2 first (full quality), falls back to HQ preview.

    Returns the path to the downloaded file.
    """
    # Try OAuth2 download (full quality original)
    oauth_token = _get_oauth_token()
    if oauth_token:
        try:
            resp = requests.get(
                f"{API_BASE}/sounds/{sound_id}/download/",
                headers={'Authorization': f'Bearer {oauth_token}'},
                allow_redirects=True,
                stream=True,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException:
            resp = None
        if resp is not None and resp.status_code == 200:
            with open(dest_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return dest_path

    # Fall back to HQ preview (MP3, no OAuth needed)
    api_key = _get_api_key()
    # First get the sound details for preview URL
    try:
        resp = requests.get(
            f"{API_BASE}/sounds/{sound_id}/",
            params={'token': api_key, 'fields': 'previews'},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        print(f"  Failed to get sound {sound_id}: {exc}")
        return None
    if resp.status_code != 200:
        print(f"  Failed to get sound {sound_id}: {resp.status_code}")
        return None

    try:
        previews = resp.json().get('previews', {})
    except ValueError:
        print(f"  Invalid preview response for sound {sound_id}")
        return None
    preview_url = previews.get('preview-hq-mp3') or previews.get('preview-lq-mp3')
    if not preview_url:
        print(f"  No preview URL for sound {sound_id}")
        return None

    # Download preview
    preview_path = dest_path + '.mp3'
    try:
        resp = requests.get(preview_url, stream=True, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        print(f"  Preview download failed: {exc}")
        return None
    if resp.status_code == 200:
        with open(preview_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return preview_path

    print(f"  Preview download failed: {resp.status_code}")
    return None


def search_and_download(query, dest_path, duration_min=0.1, duration_max=30):
    """Search for a sound and download the best match.

    Returns (downloaded_path, sound_info) or (None, None).
    """
    results = search(query, duration_min=duration_min, duration_max=duration_max)
    if not results:
        return None, None

    # Pick the first (highest relevance) result
    sound = results[0]
    downloaded = download(sound['id'], dest_path)
    return downloaded, sound
