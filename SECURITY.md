# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private vulnerability reporting
("Security" tab, "Report a vulnerability") on this repository. You get an answer within a few days.

## What Crewcut protects, and how

- **Your engine login** (`CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY`) lives only in `.env` and in the environment of
  the container. It is never written into the image, the studio folder, logs or the database, never passed as a
  command-line argument, and never sent to a rented machine. Logs are scrubbed for known secret patterns before they are
  written or shown.
- **The web UI** listens on `127.0.0.1` only. The server refuses requests with a foreign `Host` header (DNS rebinding)
  and cross-site writes (an `Origin` that is not this machine).
- **The teleprompter** port is reachable from your network so a phone can open it. It only serves the script of one
  episode and its scroll controls, behind a random per-episode token.
- **Agents run inside the container**, as the owner of the studio folder, never as root. They see the studio folder and
  the app, not your computer.
- **Rented GPUs** receive only scene code, fonts and the data a render needs; never your recordings (unless you approve
  that on a card), never keys. Every machine carries a label, a deadline and an on-machine watchdog; Crewcut deletes only
  machines with its own label. Files fetched back are scanned for secrets.
- **Money and publishing** need a card that you accept with a button. Accepting a card approves exactly the file version
  you saw (sha256).

## Supported versions

Crewcut is at version 0.1 (pre-release). Security fixes go into `main`.
