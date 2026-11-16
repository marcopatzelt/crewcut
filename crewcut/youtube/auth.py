"""Sign in with Google (OAuth for an installed app). The redirect lands on the local Crewcut server.

The user brings an OAuth client file of their own Google Cloud project (docs/youtube.md). The token is stored in the
studio state with owner-only permissions and is never shown.
"""

from __future__ import annotations

import json
import os
import secrets

from .. import config, db, paths

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def client_file():
    return paths.studio_root() / "config" / "youtube-client.json"


def token_file():
    return paths.state_dir() / "youtube-token.json"


def redirect_uri() -> str:
    port = int(os.environ.get("CREWCUT_PORT") or config.get("crewcut", "server.port", 4747))
    return f"http://localhost:{port}/oauth/youtube"


def _flow(state: str | None = None):
    from google_auth_oauthlib.flow import Flow
    if not client_file().is_file():
        raise FileNotFoundError("No YouTube client file. Follow docs/youtube.md once (about ten clicks in Google Cloud), "
                                "save the file as config/youtube-client.json in your studio folder.")
    return Flow.from_client_secrets_file(str(client_file()), scopes=SCOPES, redirect_uri=redirect_uri(), state=state)


def start() -> str:
    """The URL the user opens once. The state value protects the callback."""
    state = secrets.token_urlsafe(24)
    db.kv_set("youtube_oauth_state", state)
    url, _ = _flow(state).authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
    return url


def finish(code: str, state: str) -> None:
    expected = db.kv_get("youtube_oauth_state")
    if not expected or not secrets.compare_digest(expected, state or ""):
        raise PermissionError("The sign-in link is old or not from this studio. Start again.")
    flow = _flow(state)
    flow.fetch_token(code=code)
    creds = flow.credentials
    p = token_file()
    p.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(p, 0o600)
    db.kv_set("youtube_oauth_state", "")


def credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    p = token_file()
    if not p.is_file():
        raise FileNotFoundError("YouTube is not connected. Run `crewcut youtube auth` and open the link once.")
    creds = Credentials.from_authorized_user_info(json.loads(p.read_text(encoding="utf-8")), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        p.write_text(creds.to_json(), encoding="utf-8")
        os.chmod(p, 0o600)
    return creds


def connected() -> bool:
    return token_file().is_file()
