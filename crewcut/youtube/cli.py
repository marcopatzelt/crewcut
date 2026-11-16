"""`crewcut youtube connect | auth | upload | status`."""

from __future__ import annotations

import json
import os


def main(a) -> int:
    from . import auth
    if a.ycmd == "connect":
        from . import connect
        if auth.connected():
            print("YouTube is connected already.")
            return 0
        if a.state:
            print(json.dumps(connect.state(), indent=1))
            return 0
        episode = a.episode or os.environ.get("CREWCUT_EPISODE") or "_onboarding"
        card = connect.propose(episode)
        print(f"card #{card['id']} is open: {card['title']}" + (f" (before that: {connect.why_not()})"
                                                               if connect.why_not() else ""))
        return 0
    if a.ycmd == "auth":
        try:
            url = auth.start()
        except FileNotFoundError as e:
            print(str(e))
            return 4
        except ImportError:
            print("The YouTube libraries are missing in this image (pip extra 'youtube').")
            return 1
        print("Open this link once and allow Crewcut to upload to your channel:")
        print(url)
        return 0
    if a.ycmd == "status":
        print("connected" if auth.connected() else "not connected (say \"connect YouTube\" or run `crewcut youtube connect`)")
        print("client file: " + ("present" if auth.client_file().is_file() else "missing (crewcut youtube connect sets it "
                                 "up through Claude in Chrome; by hand: docs/youtube.md)"))
        return 0
    if a.ycmd == "upload":
        from ..conductor import queue
        from . import upload
        episode = a.episode or os.environ.get("CREWCUT_EPISODE")
        if not episode:
            print("crewcut youtube upload: which episode? Use --episode.")
            return 2
        job = os.environ.get("CREWCUT_JOB", "")

        def progress(p: float) -> None:
            if job.isdigit():
                queue.set_doing(int(job), f"Uploading to YouTube, {p * 100:.0f} %", p)

        try:
            res = upload.upload(episode, a.package or "export/upload.json", publish_at=a.schedule, dry_run=a.dry_run,
                                progress=progress)
        except PermissionError as e:
            print(str(e))
            return 3
        except FileNotFoundError as e:
            print(str(e))
            return 4
        except ValueError as e:
            print(str(e))
            return 1
        print(json.dumps(res, indent=1, ensure_ascii=False))
        return 0
    return 2
