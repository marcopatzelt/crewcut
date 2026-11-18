# Prompter on a chosen screen

In the desktop app, open Teleprompter, choose a screen once, then select **Open approved script full screen**.
The saved choice stays in desktop settings, not in the agent's studio. Escape closes the prompter window.
If that screen is disconnected, Crewcut reports an error instead of using another screen.

Drag the reading line up or down, with a mouse or touch. When it has keyboard focus, arrow keys move it by one percent.
The position stays saved for the episode and follows the remote. Moving the line does not start playback.
On the phone remote, use **Higher**, **Lower** or **Reset line** under **Reading line**.
For mirror glass, turn on **Mirror** (or press M). This preference also stays saved for the episode.

Agents may request this exact action with `crewcut prompter EPISODE --desktop`. The command returns a request ID,
not a success claim. Read the result with `crewcut prompter EPISODE --desktop-status ID`.
The desktop app must be running. Requests expire after two minutes and never start recording.

The bridge uses small request files in the studio's `.crewcut/desktop-prompter/` folder. Requests contain an episode
ID only, not commands, file destinations or URLs. The desktop validates each request, reads approval metadata from
the local server, and constructs a URL on its fixed local prompter port. The server checks the approved script hash
again before opening. This does not approve a draft or change an episode's production step.

The separate window has no Node access, no privileged preload bridge, no popups and no general desktop permissions.
The selected monitor is checked after the window enters full screen. Linux uses X11 through XWayland when DISPLAY
is available, since native Wayland window placement is controlled by the compositor. Unsupported placement fails
visibly rather than claiming the requested monitor is in use.

These request and result files are user data, not a security boundary against a process that already controls the
studio. The native capability remains restricted to the local approved-script viewer even for malformed requests.
There is no mouse control, keyboard injection, arbitrary program execution, or automatic recording.
