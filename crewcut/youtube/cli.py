"""`crewcut youtube connect | auth | upload | comment | replies | status | verify | results | retention`.

`upload` exits 0 when the video is up (also when it was up already: "status": "exists"), 3 without an accepted card,
5 while another upload of the episode runs, 6 when YouTube cannot be asked whether the video is there already."""

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
    if a.ycmd == "results":
        from .results import results
        try:
            result = results(a.episode, a.start, a.end, a.video, first_days=a.first)
        except (FileNotFoundError, ValueError, LookupError, PermissionError) as error:
            print(str(error))
            return 1
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0
    if a.ycmd == "verify":
        from .verify import verify
        try:
            result = verify(a.episode, a.package)
        except (FileNotFoundError, ValueError, LookupError) as error:
            print(str(error))
            return 1
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return 0 if result["matches"] else 1
    if a.ycmd == "replies":
        from . import replies
        if a.status:
            print(json.dumps(replies.status(a.episode), indent=1, ensure_ascii=False))
            return 0
        if replies.settings()["mode"] == "off" and not a.dry_run:
            print("Comment replies are off (youtube.cta_replies = \"off\" in config/crewcut.toml). --dry-run still "
                  "shows what would be sent.")
            return 0
        if not a.dry_run and not auth.connected():
            print("YouTube is not connected.")
            return 4
        try:
            res = replies.run(a.episode, dry_run=True if a.dry_run else None)
        except ImportError:
            print("The YouTube libraries are missing in this image (pip extra 'youtube').")
            return 1
        print(json.dumps(res, indent=1, ensure_ascii=False) if res else "No published video with a comment word "
              "(cta_keyword and cta_url in its upload) to look at.")
        return 1 if any(r.get("error") for r in res) else 0
    if a.ycmd == "comment":
        from . import upload
        try:
            res = upload.comment(a.episode, a.package, wait_s=a.wait)
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
        return 0 if res["status"] in ("added", "exists") else 1
    if a.ycmd == "retention":
        from . import analytics
        try:
            res = analytics.retention(a.episode, video=a.video)
        except analytics.NoData:
            print(analytics.NO_DATA)
            return 0
        except FileNotFoundError as e:
            print(str(e))
            return 4
        except PermissionError as e:
            print(str(e))
            return 4
        except ImportError:
            print("The YouTube libraries are missing in this image (pip extra 'youtube').")
            return 1
        print(json.dumps(res, indent=1, ensure_ascii=False) if a.json else "\n".join(analytics.lines(res)))
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

        from . import guard
        try:
            res = upload.upload(episode, a.package or "export/upload.json", publish_at=a.schedule, dry_run=a.dry_run,
                                progress=progress, new_video=getattr(a, "new_video", False))
        except guard.Busy as e:
            print(str(e))
            return 5
        except guard.CheckFailed as e:
            print(str(e))
            return 6
        except PermissionError as e:
            print(str(e))
            return 3
        except FileNotFoundError as e:
            print(str(e))
            return 4
        except ValueError as e:
            print(str(e))
            return 1
        if res.get("status") == "exists":
            print(res["message"])
        print(json.dumps(res, indent=1, ensure_ascii=False))
        return 0
    return 2
