"""Sign in with Google (OAuth for an installed app). The redirect lands on the local Crewcut server.

The user brings an OAuth client file of their own Google Cloud project (docs/youtube.md). The token is stored in the
studio state with owner-only permissions and is never shown.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from pathlib import Path

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


def _save_credentials(creds) -> None:
    destination = token_file()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=".youtube-token-", delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            stream.write(creds.to_json())
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def redirect_uri() -> str:
    port = int(os.environ.get("CREWCUT_PUBLIC_PORT") or os.environ.get("CREWCUT_PORT") or
               config.get("crewcut", "server.port", 4747))
    return f"http://localhost:{port}/oauth/youtube"


def _flow(state: str | None = None, code_verifier: str | None = None):
    from google_auth_oauthlib.flow import Flow
    if not client_file().is_file():
        raise FileNotFoundError("No YouTube client file. Follow docs/youtube.md once (about ten clicks in Google Cloud), "
                                "save the file as config/youtube-client.json in your studio folder.")
    return Flow.from_client_secrets_file(str(client_file()), scopes=SCOPES, redirect_uri=redirect_uri(), state=state,
                                        code_verifier=code_verifier, autogenerate_code_verifier=False)


def start() -> str:
    """The URL the user opens once. The state value protects the callback."""
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    url, _ = _flow(state, verifier).authorization_url(access_type="offline", prompt="consent",
                                                    include_granted_scopes="true")
    db.kv_set("youtube_oauth_verifier", verifier)
    db.kv_set("youtube_oauth_state", state)
    return url


def finish(code: str, state: str) -> None:
    expected = db.kv_get("youtube_oauth_state")
    if not expected or not secrets.compare_digest(expected, state or ""):
        raise PermissionError("The sign-in link is old or not from this studio. Start again.")
    verifier = db.kv_get("youtube_oauth_verifier")
    if not verifier:
        raise PermissionError("The sign-in link is incomplete. Start the YouTube connection again.")
    flow = _flow(state, verifier)
    flow.fetch_token(code=code)
    creds = flow.credentials
    _save_credentials(creds)
    db.kv_set("youtube_oauth_state", "")
    db.kv_set("youtube_oauth_verifier", "")


def credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    p = token_file()
    if not p.is_file():
        raise FileNotFoundError("YouTube is not connected. Run `crewcut youtube auth` and open the link once.")
    creds = Credentials.from_authorized_user_info(json.loads(p.read_text(encoding="utf-8")), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)
    return creds


def connected() -> bool:
    return token_file().is_file()
