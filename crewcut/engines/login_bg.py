"""Background device-code login for Codex: posts the link and code into the chat, then says when it worked.

Started by `crewcut engine login codex`; runs detached so no agent has to wait for the user.
"""

from __future__ import annotations

import sys

from ..conductor import flow
from . import get


def main(argv: list[str]) -> int:
    name, chat = argv[0], (argv[1] if len(argv) > 1 else flow.ONBOARDING)
    eng = get(name)
    if eng.name != "codex":
        flow.post(chat, "Claude connects with the Connect Claude button: on the start page, or in the desktop app's "
                        "settings. On a server you can also put a `claude setup-token` token into .env.")
        return 0

    def tell(url: str, code: str | None) -> None:
        flow.post(chat, f"To connect Codex, open {url} and enter the code {code or '(shown on the page)'}. "
                        "Device-code login has to be on in your ChatGPT security settings.")

    ok, why = eng.device_login(tell)
    flow.post(chat, "Codex is connected. New work runs on Codex (beta)." if ok else f"Codex is not connected: {why}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
