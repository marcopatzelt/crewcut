"""`crewcut motion ...`: motion graphics with EffectCraft, the open-source After Effects-style compositor.

Every command drives the real engine through its native ``effectcraft-cli`` (engine commands, AE-style
scripts, the renderer). The ``.ecproj`` file is the state; the session file adds the active comp, history and
snapshot undo. ``--json`` gives machine output; ``--dry-run`` runs a mutation in EffectCraft without saving it;
``--persistent`` keeps one ``effectcraft-cli mcp`` process for all engine calls of the command.

    crewcut motion info
    crewcut motion project new|open|info|save|profiles
    crewcut motion comp new|list|use|set|motion-blur|info
    crewcut motion layer add solid|text|shape|footage|null|camera|light|precomp
    crewcut motion layer props|get|set|switch|timing|parent|matte|blend
    crewcut motion key set LAYER PATH t=v ... [--ease E] [--influence O,I] [--spring]
    crewcut motion expr set|preset
    crewcut motion effect apply|list|params
    crewcut motion text animator
    crewcut motion precompose LAYERS --name N
    crewcut motion template list|show
    crewcut motion run-template NAME --params JSON|@file [--loose] [--keep-script F]
    crewcut motion render frame|sheet|compare|video|palette
    crewcut motion session status|undo|redo|history
    crewcut motion exec ID --params JSON [--read-only] | batch steps.json | script file.jsx [--with-lib] | commands

The motion workflow (no engine; docs/motion-workflow.md):

    crewcut motion plan EPISODE [--short] | --check [--file F] [--card]
    crewcut motion library [--no-episodes]
    crewcut motion new EPISODE INSERT_ID --from brief.md
    crewcut motion style-frame EPISODE INSERT_ID --ours F [--ours F] [--ref F] [--natural]
    crewcut motion promote EPISODE INSERT_ID --name NAME [--title T]
    crewcut motion report EPISODE --skeleton | --from F
    crewcut motion lessons
    crewcut motion reference add LINK_OR_FILE --reason R [--by user|scout] [--episode E] | from-chat | list

Exit codes: 0 ok, 1 error, 2 usage, 3 `render palette` found one hue above the limit (plain output only).
"""

from __future__ import annotations

import functools
import json
import os
import sys
from typing import Any

import click

from .. import __version__
from . import effect as fx
from . import export as ex
from . import keyframe as kf
from . import layer as ly
from . import palette as pal
from . import project as pj
from . import templates as tp
from . import text as tx
from .backend import Backend, BackendError
from .jsx import parse_result, wrap_program
from .session import Session

ERRORS = (BackendError, RuntimeError, ValueError, tp.TemplateError, kf.KeyError_, OSError)


# ── plain output (stdout for results, stderr for warnings and errors) ────

def say(msg: str) -> None:
    click.echo(msg)


def warn(msg: str) -> None:
    click.echo(f"warning: {msg}", err=True)


def fail(msg: str) -> None:
    click.echo(f"error: {msg}", err=True)


class App:
    """Process state: options, backend and session."""

    def __init__(self, use_json: bool, project: str | None, session: str | None, cli: str | None, gpu: bool,
                 dry_run: bool, templates_dir: str | None, persistent: bool = False):
        self.persistent = persistent
        self.json = use_json
        self.dry_run = dry_run
        self.templates_dir = templates_dir
        self.backend = Backend(cli=cli, gpu=gpu)
        self.session = Session.load(session, project)

    # ── helpers ──────────────────────────────────────────────────────────
    def project(self) -> str:
        p = self.session.require_project()
        if self.persistent and not self.dry_run:
            self.ensure_engine(p)
        return p

    def ensure_engine(self, project: str) -> None:
        """Keep one engine process with this project loaded (--persistent)."""
        from .engine import McpEngine
        e = self.backend.engine
        try:
            if e is None or not e.alive():
                self.backend.engine = McpEngine(project, cli=self.backend.cli, gpu=self.backend.gpu)
            elif e.project != os.path.abspath(project):
                e.reopen(project)
        except BackendError as err:              # fall back to one-shot calls, say so once
            if e is None:
                warn(f"persistent engine unavailable, using one-shot calls: {err}")
            self.backend.engine = None
            self.persistent = False

    def reload_engine(self) -> None:
        """After undo/redo replaced the file on disk."""
        if self.backend.engine is not None and self.session.project:
            self.backend.engine.reopen(self.session.project)

    def close(self) -> None:
        """Stop the persistent engine process, if one runs."""
        if self.backend.engine is not None:
            self.backend.engine.close()
            self.backend.engine = None

    def comp(self, given: str | None) -> str:
        return self.session.require_comp(given)

    def program(self, body: str, label: str, mutate: bool = True) -> Any:
        """Run a script body (with ec_lib.jsx) inside EffectCraft; snapshot + save unless --dry-run."""
        code = wrap_program(body, tp.lib_source())
        return self._mutate(label, lambda save: parse_result(
            self.backend.script(code, project=self.project(), save=save)), mutate)

    def steps(self, steps: list[dict], label: str) -> Any:
        return self._mutate(label, lambda save: self.backend.run_steps(steps, project=self.project(), save=save))

    def _mutate(self, label: str, fn, mutate: bool = True) -> Any:
        self.project()
        if mutate and not self.dry_run:
            self.session.snapshot(label)
        try:
            res = fn(mutate and not self.dry_run)
        except Exception:
            if mutate and not self.dry_run:          # nothing changed on disk; drop the unused snapshot
                snaps = self.session.data.get("snapshots", [])
                if snaps:
                    try:
                        os.remove(snaps.pop()["file"])
                    except OSError:
                        pass
                    self.session.data["pos"] = len(snaps) - 1
            raise
        self.session.record(label, res)
        return res


def out(app: App, data: Any, human: str | None = None) -> None:
    if app.json:
        click.echo(json.dumps(data, ensure_ascii=False, default=str))
    elif human is not None:
        say(human)
    elif isinstance(data, (dict, list)):
        click.echo(json.dumps(data, indent=1, ensure_ascii=False, default=str))
    else:
        click.echo(str(data))


def handle_error(f):
    @functools.wraps(f)
    def wrapper(*a, **k):
        ctx = click.get_current_context()
        app: App | None = ctx.obj
        try:
            return f(*a, **k)
        except click.exceptions.Exit:            # a deliberate exit code (click's Exit is a RuntimeError)
            raise
        except ERRORS as exc:
            msg = str(exc)
            if app is not None and app.json:
                payload = {"error": msg}
                if isinstance(exc, BackendError) and exc.detail is not None:
                    payload["detail"] = exc.detail
                click.echo(json.dumps(payload, ensure_ascii=False, default=str))
            else:
                fail(msg)
            ctx.exit(1)
    return wrapper


def parse_json_opt(text: str | None, what: str) -> Any:
    if text is None:
        return None
    if text.startswith("@"):
        with open(text[1:], encoding="utf-8") as f:
            text = f.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"{what}: not JSON ({e})") from e


def lay(v: str) -> Any:
    """Layer reference: an id (digits), '#n' or a name."""
    return int(v) if v.isdigit() else v


# ── root group ───────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Machine-readable JSON output.")
@click.option("--project", "project", type=str, default=None, help="Project file (.ecproj).")
@click.option("--session", "session", type=str, default=None, help="Session file (default <project>.cli-session.json).")
@click.option("--cli", "cli_path", type=str, default=None, help="Path of effectcraft-cli (else $EFFECTCRAFT_CLI, PATH).")
@click.option("--gpu", is_flag=True, help="Render on the GPU compositor.")
@click.option("--dry-run", "dry_run", is_flag=True, help="Run mutations in EffectCraft without saving them.")
@click.option("--templates-dir", type=str, default=None,
              help="Extra template folder(s), ':'-separated; searched before the style pack and the app.")
@click.option("--persistent", is_flag=True, help="Keep one engine process with the project loaded.")
@click.version_option(__version__, prog_name="crewcut motion")
@click.pass_context
def cli(ctx, use_json, project, session, cli_path, gpu, dry_run, templates_dir, persistent):
    """Motion graphics with EffectCraft: compositions, layers, keys, effects, templates, rendering."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)
    ctx.obj = App(use_json, project, session, cli_path, gpu, dry_run, templates_dir, persistent)
    ctx.call_on_close(ctx.obj.close)


@cli.result_callback()
@click.pass_context
def _autosave(ctx, *_a, **_k):
    """Persist the session after a command (the engine already saved the project)."""
    app: App = ctx.obj
    if app is None or app.dry_run:
        return
    if app.session._modified and app.session.path:
        try:
            app.session.save()
        except OSError as e:
            warn(f"session not saved: {e}")


@cli.command("info")
@click.pass_obj
@handle_error
def info_cmd(app: App):
    """Backend version, binary, and project summary."""
    data = {"harness": __version__, "binary": app.backend.binary, "version": app.backend.version(),
            "session": app.session.status()}
    if app.session.project and os.path.exists(app.session.project):
        data["engine"] = app.backend.info(app.session.project)
    out(app, data)


# ── project ──────────────────────────────────────────────────────────────

@cli.group("project")
def project_grp():
    """Create, open and inspect projects."""


@project_grp.command("new")
@click.option("-o", "--out", "path", required=True, help="Project file to write (.ecproj).")
@click.option("--comp", "name", default="Main", show_default=True)
@click.option("--profile", default="1080p60", show_default=True, help="See: project profiles")
@click.option("--width", type=int)
@click.option("--height", type=int)
@click.option("--fps", type=float)
@click.option("--duration", type=float, default=10.0, show_default=True)
@click.option("--bg", help="Background colour #hex.")
@click.option("--shutter-angle", type=float, default=180.0, show_default=True)
@click.option("--samples", type=int, default=16, show_default=True, help="Motion blur samples per frame.")
@click.option("--renderer", type=click.Choice(["classic3D", "advanced3D"]))
@click.option("--no-motion-blur", is_flag=True)
@click.option("--overwrite", is_flag=True)
@click.pass_obj
@handle_error
def project_new(app: App, path, name, profile, width, height, fps, duration, bg, shutter_angle, samples, renderer,
                no_motion_blur, overwrite):
    """New project with one composition (written by EffectCraft)."""
    params = pj.comp_params(name, profile, width, height, fps, duration, bg, shutter_angle, samples, renderer)
    r = pj.create(app.backend, path, params, motion_blur=not no_motion_blur, overwrite=overwrite)
    app.session = Session.load(None, r["project"])
    app.session.use_comp(name)
    app.session.record("project new", r["project"])
    out(app, {"project": r["project"], "comp": name, "settings": params}, f"created {r['project']} ({name})")


@project_grp.command("open")
@click.argument("path")
@click.pass_obj
@handle_error
def project_open(app: App, path):
    """Make PATH the session's project."""
    if not os.path.exists(path):
        raise RuntimeError(f"no such project: {path}")
    app.session = Session.load(None, path)
    app.session._modified = True
    out(app, app.session.status(), f"opened {os.path.abspath(path)}")


@project_grp.command("info")
@click.pass_obj
@handle_error
def project_info(app: App):
    """Engine summary of the project (comps, layers, renderer)."""
    out(app, app.backend.info(app.project()))


@project_grp.command("save")
@click.option("--as", "save_as", required=True, help="Copy the project to a new file (engine save).")
@click.pass_obj
@handle_error
def project_save(app: App, save_as):
    """Save a copy under a new name (EffectCraft writes it) and switch the session to it."""
    r = app.backend.call(app.backend.argv(["info"], project=app.project(), save_as=save_as))
    app.session.set_project(save_as)
    out(app, {"project": os.path.abspath(save_as), "reply": r}, f"saved {save_as}")


@project_grp.command("profiles")
@click.pass_obj
@handle_error
def project_profiles(app: App):
    """Composition presets."""
    out(app, pj.list_profiles())


# ── comp ─────────────────────────────────────────────────────────────────

@cli.group("comp")
def comp_grp():
    """Compositions."""


@comp_grp.command("new")
@click.argument("name")
@click.option("--profile", default="1080p60", show_default=True)
@click.option("--width", type=int)
@click.option("--height", type=int)
@click.option("--fps", type=float)
@click.option("--duration", type=float, default=5.0, show_default=True)
@click.option("--bg")
@click.option("--shutter-angle", type=float, default=180.0)
@click.option("--samples", type=int, default=16)
@click.option("--renderer", type=click.Choice(["classic3D", "advanced3D"]))
@click.option("--no-motion-blur", is_flag=True)
@click.option("--use/--no-use", default=True, help="Make it the session's active comp.")
@click.pass_obj
@handle_error
def comp_new(app: App, name, profile, width, height, fps, duration, bg, shutter_angle, samples, renderer, no_motion_blur, use):
    """New composition in the project."""
    params = pj.comp_params(name, profile, width, height, fps, duration, bg, shutter_angle, samples, renderer)
    steps = [{"command": "comp.new", "params": params}]
    if not no_motion_blur:
        steps.append({"command": "comp.setSwitch", "params": {"comp": name, "switch": "motionBlur", "value": True}})
    r = app.steps(steps, f"comp new {name}")
    if use:
        app.session.use_comp(name)
    out(app, {"comp": name, "settings": params, "reply": r}, f"comp {name}")


@comp_grp.command("list")
@click.pass_obj
@handle_error
def comp_list(app: App):
    """Comps in the project (from the engine)."""
    out(app, app.backend.info(app.project()))


@comp_grp.command("use")
@click.argument("name")
@click.pass_obj
@handle_error
def comp_use(app: App, name):
    """Set the active comp for later commands."""
    app.session.use_comp(name)
    out(app, {"comp": name}, f"active comp {name}")


@comp_grp.command("set")
@click.option("--comp", "comp")
@click.option("--params", "params", required=True, help="JSON for comp.settings, e.g. {\"duration\": 20}.")
@click.pass_obj
@handle_error
def comp_set(app: App, comp, params):
    """Change composition settings (comp.settings)."""
    p = parse_json_opt(params, "--params") or {}
    p["comp"] = app.comp(comp)
    out(app, app.steps([{"command": "comp.settings", "params": p}], "comp set"))


@comp_grp.command("motion-blur")
@click.argument("state", type=click.Choice(["on", "off"]))
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def comp_mb(app: App, state, comp):
    """Comp motion blur switch."""
    c = app.comp(comp)
    out(app, app.steps([{"command": "comp.setSwitch", "params": {"comp": c, "switch": "motionBlur", "value": state == "on"}}],
                       f"motion blur {state}"))


@comp_grp.command("info")
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def comp_info(app: App, comp):
    """Settings and layers of a comp (comp.info)."""
    out(app, app.backend.exec("comp.info", {"comp": app.comp(comp)}, project=app.project(), save=False))


# ── layers ───────────────────────────────────────────────────────────────

@cli.group("layer")
def layer_grp():
    """Layers: add, inspect, switches, timing, parenting, mattes."""


def _common_layer_opts(f):
    for opt in reversed([
        click.option("--comp", "comp"), click.option("--name"),
        click.option("--in", "in_", type=float, help="In point (s)."), click.option("--out", "out_", type=float, help="Out point (s)."),
        click.option("--3d", "three_d", is_flag=True, help="3D layer."), click.option("--mb", is_flag=True, help="Motion blur switch on."),
        click.option("--blend", help="Blend mode, e.g. Screen, Add."),
        click.option("--pos", help="Position x,y[,z]."), click.option("--scale", help="Scale % x,y[,z]."),
        click.option("--opacity", type=float), click.option("--rot", type=float, help="Rotation (deg)."),
    ]):
        f = opt(f)
    return f


def _common(app: App, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot) -> dict:
    o: dict[str, Any] = {"name": name, "in": in_, "out": out_, "blend": blend, "opacity": opacity, "rot": rot}
    if three_d:
        o["threeD"] = True
    if mb:
        o["mb"] = True
    if pos:
        o["pos"] = kf.parse_value(pos)
    if scale:
        o["scale"] = kf.parse_value(scale)
    return o


def _add(app: App, kind: str, comp: str | None, opts: dict) -> None:
    c = app.comp(comp)
    o = ly.options(kind, **opts)
    r = app.program(ly.add_program(c, kind, o), f"layer add {kind}")
    out(app, r, f"{kind} layer {r.get('layer') if isinstance(r, dict) else r}")


@layer_grp.group("add")
def layer_add():
    """Add a layer: solid, text, shape, footage, null, camera, light, precomp."""


@layer_add.command("solid")
@_common_layer_opts
@click.option("--color", default="#ffffff")
@click.option("--w", type=int)
@click.option("--h", type=int)
@click.pass_obj
@handle_error
def add_solid(app, comp, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot, color, w, h):
    o = _common(app, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot)
    o.update(color=color, w=w, h=h)
    _add(app, "solid", comp, o)


@layer_add.command("text")
@_common_layer_opts
@click.option("--text", required=True)
@click.option("--font", default="Inter", help="Font family (the neutral pack uses Inter).")
@click.option("--style", default="ExtraBold")
@click.option("--size", type=float, default=120)
@click.option("--fill", default="#111111")
@click.option("--tracking", type=float)
@click.option("--justify", type=click.Choice(["left", "center", "right"]))
@click.pass_obj
@handle_error
def add_text(app, comp, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot, text, font, style, size, fill, tracking, justify):
    o = _common(app, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot)
    o.update(text=text, font=font, style=style, size=size, fill=fill, tracking=tracking, justify=justify)
    _add(app, "text", comp, o)


@layer_add.command("shape")
@_common_layer_opts
@click.option("--kind", "shape_kind", default="rect", type=click.Choice(list(ly.SHAPES)))
@click.option("--size", help="w,h")
@click.option("--fill")
@click.option("--stroke")
@click.option("--stroke-width", type=float)
@click.pass_obj
@handle_error
def add_shape(app, comp, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot, shape_kind, size, fill, stroke, stroke_width):
    o = _common(app, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot)
    o.update(kind=shape_kind, size=kf.parse_value(size) if size else None, fill=fill, stroke=stroke, strokeWidth=stroke_width)
    _add(app, "shape", comp, o)


@layer_add.command("footage")
@_common_layer_opts
@click.option("--path", required=True, help="Image, video, SVG or first frame of a sequence.")
@click.option("--sequence", is_flag=True, help="Import a numbered image sequence.")
@click.option("--frame-rate", type=float, help="Sequence frame rate.")
@click.pass_obj
@handle_error
def add_footage(app, comp, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot, path, sequence, frame_rate):
    o = _common(app, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot)
    o.update(path=os.path.abspath(path), sequence=sequence or None, frameRate=frame_rate)
    _add(app, "footage", comp, o)


@layer_add.command("null")
@_common_layer_opts
@click.pass_obj
@handle_error
def add_null(app, comp, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot):
    _add(app, "null", comp, _common(app, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot))


@layer_add.command("camera")
@_common_layer_opts
@click.option("--preset", help="15mm..200mm")
@click.option("--zoom", type=float)
@click.option("--dof", is_flag=True)
@click.option("--focus", "focus", type=float, help="Focus distance (px).")
@click.option("--aperture", type=float)
@click.option("--blur-level", type=float)
@click.option("--poi", help="Point of interest x,y,z.")
@click.option("--one-node", is_flag=True)
@click.pass_obj
@handle_error
def add_camera(app, comp, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot, preset, zoom, dof, focus, aperture, blur_level, poi, one_node):
    o = _common(app, name, in_, out_, False, False, None, None, None, None, None)
    o.update(preset=preset, zoom=zoom, dof=dof or None, focusDistance=focus, aperture=aperture, blurLevel=blur_level,
             position=kf.parse_value(pos) if pos else None, poi=kf.parse_value(poi) if poi else None,
             type="oneNode" if one_node else None)
    _add(app, "camera", comp, o)


@layer_add.command("light")
@_common_layer_opts
@click.option("--kind", "light_kind", default="Point", type=click.Choice(list(ly.LIGHTS)))
@click.option("--color")
@click.option("--intensity", type=float)
@click.option("--shadows", is_flag=True)
@click.option("--shadow-diffusion", type=float)
@click.option("--poi")
@click.pass_obj
@handle_error
def add_light(app, comp, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot, light_kind, color, intensity, shadows, shadow_diffusion, poi):
    o = _common(app, name, in_, out_, False, False, None, None, None, None, None)
    o.update(kind=light_kind, color=color, intensity=intensity, castsShadows=shadows or None, shadowDiffusion=shadow_diffusion,
             position=kf.parse_value(pos) if pos else None, poi=kf.parse_value(poi) if poi else None)
    _add(app, "light", comp, o)


@layer_add.command("precomp")
@_common_layer_opts
@click.option("--source", required=True, help="Name of the comp to nest.")
@click.pass_obj
@handle_error
def add_precomp(app, comp, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot, source):
    o = _common(app, name, in_, out_, three_d, mb, blend, pos, scale, opacity, rot)
    o["source"] = source
    _add(app, "precomp", comp, o)


@layer_grp.command("props")
@click.argument("layer")
@click.option("--comp", "comp")
@click.option("--time", type=float)
@click.pass_obj
@handle_error
def layer_props(app: App, layer, comp, time):
    """A layer's property tree with paths (flat)."""
    out(app, app.backend.props(app.project(), app.comp(comp), layer, flat=True, time=time))


@layer_grp.command("get")
@click.argument("layer")
@click.argument("path")
@click.option("--comp", "comp")
@click.option("--time", type=float)
@click.pass_obj
@handle_error
def layer_get(app: App, layer, path, comp, time):
    """Read a property (value at time, keys, expression)."""
    out(app, app.backend.get(app.project(), app.comp(comp), layer, path, time))


@layer_grp.command("set")
@click.argument("layer")
@click.argument("path")
@click.argument("value")
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def layer_set(app: App, layer, path, value, comp):
    """Set a static property value (JSON or x,y)."""
    c = app.comp(comp)
    out(app, app.steps([{"command": "prop.set", "params": {"comp": c, "layer": lay(layer), "path": path,
                                                            "value": kf.parse_value(value)}}], f"set {layer} {path}"))


@layer_grp.command("switch")
@click.argument("layer")
@click.argument("switch", type=click.Choice(list(ly.SWITCHES)))
@click.argument("state", type=click.Choice(["on", "off"]))
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def layer_switch(app: App, layer, switch, state, comp):
    """Layer switches: threeD, motionBlur, adjustment, collapse..."""
    out(app, app.steps(ly.switch_steps(app.comp(comp), lay(layer), switch, state == "on"), f"switch {switch}"))


@layer_grp.command("timing")
@click.argument("layer")
@click.option("--in", "in_", type=float)
@click.option("--out", "out_", type=float)
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def layer_timing(app: App, layer, in_, out_, comp):
    """Trim in/out points (comp seconds)."""
    out(app, app.steps(ly.timing_steps(app.comp(comp), lay(layer), in_, out_), "timing"))


@layer_grp.command("parent")
@click.argument("layer")
@click.argument("parent")
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def layer_parent(app: App, layer, parent, comp):
    """Parent LAYER to PARENT ('none' to clear)."""
    par = None if parent.lower() == "none" else lay(parent)
    out(app, app.steps([{"command": "layer.setParent", "params": {"comp": app.comp(comp), "layers": [lay(layer)], "parent": par}}], "parent"))


@layer_grp.command("matte")
@click.argument("layer")
@click.argument("matte")
@click.option("--kind", type=click.Choice(["alpha", "alphaInverted", "luma", "lumaInverted"]), default="alpha")
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def layer_matte(app: App, layer, matte, kind, comp):
    """Track matte: LAYER shows through MATTE ('none' to clear)."""
    m = None if matte.lower() == "none" else lay(matte)
    out(app, app.steps([{"command": "layer.setTrackMatte", "params": {"comp": app.comp(comp), "layer": lay(layer), "matte": m, "kind": kind}}], "matte"))


@layer_grp.command("blend")
@click.argument("layer")
@click.argument("mode")
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def layer_blend(app: App, layer, mode, comp):
    """Blend mode (Screen, Add, Multiply, Overlay...)."""
    if mode not in ly.BLEND_MODES:
        raise ValueError(f"blend mode must be one of {', '.join(ly.BLEND_MODES)}")
    out(app, app.steps([{"command": "layer.setBlendMode", "params": {"comp": app.comp(comp), "layers": [lay(layer)], "mode": mode}}], "blend"))


# ── keyframes and expressions ────────────────────────────────────────────

@cli.group("key")
def key_grp():
    """Keyframes with easing."""


@key_grp.command("set")
@click.argument("layer")
@click.argument("path")
@click.argument("keys", nargs=-1, required=True)
@click.option("--ease", default="smooth", show_default=True, type=click.Choice(list(kf.EASES)))
@click.option("--influence", help="Explicit out,in influence %, e.g. 5,95 (overrides --ease).")
@click.option("--spring", is_flag=True, help="Add an overshoot spring after the last key.")
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def key_set(app: App, layer, path, keys, ease, influence, spring, comp):
    """Add keys TIME=VALUE (comp seconds), e.g. transform/position 0=200,540 0.6=960,540 --ease expo."""
    c = app.comp(comp)
    infl = tuple(float(x) for x in influence.split(",")) if influence else None
    if infl is not None and len(infl) != 2:
        raise ValueError("--influence takes OUT,IN")
    body = kf.key_program(c, lay(layer), path, kf.parse_keys(list(keys)), kf.resolve_ease(ease, infl), spring)
    r = app.program(body, f"keys {layer} {path}")
    out(app, {"keys": len(keys), "ease": ease, "reply": r}, f"{len(keys)} keys on {layer} {path}")


@cli.group("expr")
def expr_grp():
    """Expressions."""


@expr_grp.command("set")
@click.argument("layer")
@click.argument("path")
@click.argument("code")
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def expr_set(app: App, layer, path, code, comp):
    """Set an expression (JavaScript, AE expression model)."""
    out(app, app.steps([{"command": "prop.setExpression", "params": {"comp": app.comp(comp), "layer": lay(layer), "path": path, "expression": code}}], "expression"))


@expr_grp.command("preset")
@click.argument("layer")
@click.argument("path")
@click.argument("preset", type=click.Choice(list(kf.EXPRESSION_PRESETS)))
@click.option("--params", "params", help="JSON, e.g. {\"freq\": 3, \"amp\": 10}")
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def expr_preset(app: App, layer, path, preset, params, comp):
    """wiggle / loop / spring / time expression with parameters."""
    code = kf.expression(preset, **(parse_json_opt(params, "--params") or {}))
    r = app.steps([{"command": "prop.setExpression", "params": {"comp": app.comp(comp), "layer": lay(layer), "path": path, "expression": code}}], f"expr {preset}")
    out(app, {"expression": code, "reply": r})


# ── effects ──────────────────────────────────────────────────────────────

@cli.group("effect")
def effect_grp():
    """Effects (308 in EffectCraft)."""


@effect_grp.command("apply")
@click.argument("layer")
@click.argument("effect")
@click.option("--values", help="JSON {paramId: value}; see effect params NAME.")
@click.option("--keys", "keys", help="JSON {paramId: [[t, v], ...]}.")
@click.option("--ease", default="smooth", type=click.Choice(list(kf.EASES)))
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def effect_apply(app: App, layer, effect, values, keys, ease, comp):
    """Apply EFFECT (name, id or alias: glow, shatter, particles3d...) to LAYER with values/keys."""
    body = fx.apply_program(app.comp(comp), lay(layer), effect, parse_json_opt(values, "--values"),
                            parse_json_opt(keys, "--keys"), ease)
    out(app, app.program(body, f"effect {effect}"))


@effect_grp.command("list")
@click.option("--filter", "filt")
@click.pass_obj
@handle_error
def effect_list(app: App, filt):
    """Effect catalog from the engine (name, id, category)."""
    cat = app.backend.exec("effect.list", {})
    items = fx.find(cat, filt) if filt else (cat.get("effects", cat) if isinstance(cat, dict) else cat)
    out(app, [{"name": e.get("name"), "id": e.get("id"), "category": e.get("category")} for e in items])


@effect_grp.command("params")
@click.argument("effect")
@click.pass_obj
@handle_error
def effect_params(app: App, effect):
    """Parameter ids and defaults of one effect."""
    cat = app.backend.exec("effect.list", {})
    name = fx.resolve(effect)
    hits = [e for e in (cat.get("effects", cat) if isinstance(cat, dict) else cat)
            if e.get("name", "").lower() == name.lower() or e.get("id") == name]
    if not hits:
        raise ValueError(f"no effect {effect!r}; try: effect list --filter {effect}")
    out(app, hits[0])


# ── text ─────────────────────────────────────────────────────────────────

@cli.group("text")
def text_grp():
    """Text animators."""


@text_grp.command("animator")
@click.argument("layer")
@click.option("--props", required=True, help="Comma list: opacity,position,scale,fillColor,tracking,blur...")
@click.option("--values", help="JSON {property: value} for the animator's properties.")
@click.option("--range", "range_keys", help="JSON {start|end|offset: [[t, v], ...]} range selector keys.")
@click.option("--name")
@click.option("--ease", default="linear", type=click.Choice(list(kf.EASES)))
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def text_animator(app: App, layer, props, values, range_keys, name, ease, comp):
    """Per-character animator with a keyed range selector (typewriter, colour wave, cascade)."""
    body = tx.animator_program(app.comp(comp), lay(layer), [p.strip() for p in props.split(",") if p.strip()],
                               parse_json_opt(values, "--values"), parse_json_opt(range_keys, "--range"), name, ease)
    out(app, app.program(body, "text animator"))


# ── precompose ───────────────────────────────────────────────────────────

@cli.command("precompose")
@click.argument("layers", nargs=-1, required=True)
@click.option("--name", required=True)
@click.option("--comp", "comp")
@click.option("--leave", is_flag=True, help="Leave attributes in the outer comp.")
@click.pass_obj
@handle_error
def precompose_cmd(app: App, layers, name, comp, leave):
    """Pre-compose LAYERS into a new comp NAME."""
    out(app, app.steps([{"command": "layer.precompose", "params": {"comp": app.comp(comp), "layers": [lay(x) for x in layers],
                                                                   "name": name, "mode": "leave" if leave else "move"}}], f"precompose {name}"))


# ── templates ────────────────────────────────────────────────────────────

@cli.group("template")
def template_grp():
    """Motion templates (parameterised JSX)."""


@template_grp.command("list")
@click.pass_obj
@handle_error
def template_list(app: App):
    """Templates on the search path: --templates-dir folders, then the style pack, then the app."""
    ts = tp.discover(app.templates_dir)
    out(app, [{"name": t["name"], "description": t["description"], "kind": t["kind"], "formats": t["formats"],
               "version": t["version"], "path": t["path"]} for t in ts.values()])


@template_grp.command("show")
@click.argument("name")
@click.pass_obj
@handle_error
def template_show(app: App, name):
    """Description and default parameters of a template."""
    ts = tp.discover(app.templates_dir)
    if name not in ts:
        raise ValueError(f"unknown template {name!r}; available: {', '.join(sorted(ts))}")
    out(app, ts[name])


@cli.command("run-template")
@click.argument("name")
@click.option("--params", "params", default="{}", help="JSON (or @file.json) over the template defaults.")
@click.option("--loose", is_flag=True, help="Accept parameters the template does not declare.")
@click.option("--keep-script", help="Also write the generated script to this path.")
@click.option("--context", "context", default=None,
              help="JSON (or @file.json): the insert's context for CC.* (format, size, fps, duration, face, brand).")
@click.pass_obj
@handle_error
def run_template(app: App, name, params, loose, keep_script, context):
    """Run motion template NAME in the project (one undo step)."""
    code, merged = tp.program(name, parse_json_opt(params, "--params") or {}, app.templates_dir, strict=not loose,
                              context=parse_json_opt(context, "--context") if context else None)
    if keep_script:
        with open(keep_script, "w", encoding="utf-8") as f:
            f.write(code)
    res = app._mutate(f"template {name}", lambda save: parse_result(app.backend.script(code, project=app.project(), save=save,
                                                                                         name=f"{name}.jsx")))
    out(app, {"template": name, "params": merged, "result": res}, f"template {name} done")


# ── raw engine access ────────────────────────────────────────────────────

@cli.command("exec")
@click.argument("command_id")
@click.option("--params", "params", default="{}")
@click.option("--read-only", is_flag=True, help="Do not save (queries).")
@click.pass_obj
@handle_error
def exec_cmd(app: App, command_id, params, read_only):
    """Run one engine command by id (see: commands)."""
    p = parse_json_opt(params, "--params") or {}
    if read_only:
        out(app, app.backend.exec(command_id, p, project=app.session.project, save=False))
    else:
        out(app, app.steps([{"command": command_id, "params": p}], f"exec {command_id}"))


@cli.command("commands")
@click.option("--filter", "filt")
@click.pass_obj
@handle_error
def commands_cmd(app: App, filt):
    """The engine's command registry (ids, params)."""
    out(app, app.backend.commands(filt))


@cli.command("batch")
@click.argument("steps_file")
@click.pass_obj
@handle_error
def batch_cmd(app: App, steps_file):
    """Run engine steps from a JSON file ([{"command": id, "params": {...}}, ...]) in one process."""
    steps = parse_json_opt("@" + steps_file, "steps")
    if not isinstance(steps, list):
        raise ValueError("steps file must hold a JSON array")
    out(app, app.steps(steps, f"batch {os.path.basename(steps_file)}"))


@cli.command("script")
@click.argument("jsx_file")
@click.option("--with-lib", is_flag=True, help="Prepend ec_lib.jsx (EC.* helpers).")
@click.pass_obj
@handle_error
def script_cmd(app: App, jsx_file, with_lib):
    """Run an After Effects-style script file in the project."""
    code = open(jsx_file, encoding="utf-8").read()
    if with_lib:
        code = tp.lib_source() + "\n" + code
    out(app, app._mutate(f"script {os.path.basename(jsx_file)}", lambda save: app.backend.script(code, project=app.project(), save=save)))


# ── render ───────────────────────────────────────────────────────────────

@cli.group("render")
def render_grp():
    """Frames, sheets and videos from EffectCraft's renderer."""


@render_grp.command("frame")
@click.option("--time", "t", type=float, default=0.0)
@click.option("--out", "out_path", required=True)
@click.option("--max-side", type=int)
@click.option("--transparent", is_flag=True)
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def render_frame(app: App, t, out_path, max_side, transparent, comp):
    """One frame as PNG."""
    r = app.backend.render_frame(app.project(), os.path.abspath(out_path), comp=app.comp(comp), time=t, max_side=max_side, transparent=transparent)
    if not os.path.exists(out_path):
        raise BackendError(f"no frame written to {out_path}", detail=r)
    out(app, {"output": os.path.abspath(out_path), "bytes": os.path.getsize(out_path), "reply": r}, f"frame {out_path}")


@render_grp.command("sheet")
@click.option("--times", required=True, help="Comma list of comp seconds.")
@click.option("--out", "out_path", required=True)
@click.option("--cols", type=int, default=4)
@click.option("--max-side", type=int, default=640)
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def render_sheet(app: App, times, out_path, cols, max_side, comp):
    """Contact sheet of several moments."""
    ts = [float(x) for x in times.split(",") if x.strip()]
    out(app, ex.contact_sheet(app.backend, app.project(), app.comp(comp), ts, out_path, cols, max_side))


@render_grp.command("compare")
@click.option("--ref", required=True, help="Reference video.")
@click.option("--ref-times", required=True)
@click.option("--times", required=True)
@click.option("--out", "out_path", required=True)
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def render_compare(app: App, ref, ref_times, times, out_path, comp):
    """Reference | ours side by side, one row per moment."""
    ts = [float(x) for x in times.split(",")]
    rts = [float(x) for x in ref_times.split(",")]
    out(app, ex.compare_sheet(app.backend, app.project(), app.comp(comp), ts, ref, rts, out_path))


@render_grp.command("video")
@click.option("--out", "out_path", required=True)
@click.option("--start", type=float, default=0.0)
@click.option("--end", type=float, required=True)
@click.option("--fps", type=float, default=60.0)
@click.option("--preset", default="h264-hq", type=click.Choice(list(ex.EXPORT_PRESETS)))
@click.option("--chunk", type=float, default=4.0, show_default=True, help="Seconds per render process.")
@click.option("--jobs", type=int, default=1, show_default=True, help="Chunks rendered in parallel.")
@click.option("--crf", type=int)
@click.option("--comp", "comp")
@click.pass_obj
@handle_error
def render_video(app: App, out_path, start, end, fps, preset, chunk, jobs, crf, comp):
    """Render a range in chunks (fresh process each) and join them."""
    out(app, ex.render_video(app.backend, app.project(), out_path, app.comp(comp), start, end, fps, preset, chunk, jobs, crf))


@render_grp.command("palette")
@click.argument("image")
@click.option("--limit", type=float, default=0.30, show_default=True, help="Max share of one hue among coloured pixels.")
@click.pass_context
@handle_error
def render_palette(ctx, image, limit):
    """Hue check: share of the dominant hue among coloured pixels (exit 3 above --limit, plain output)."""
    app: App = ctx.obj
    r = pal.hue_report(image, limit)
    out(app, r, f"dominant hue {r['dominant_hue']}° holds {r['dominant_share']:.0%} of coloured pixels ({'ok' if r['ok'] else 'REWORK'})")
    if not r["ok"] and not app.json:
        ctx.exit(3)


# ── session ──────────────────────────────────────────────────────────────

@cli.group("session")
def session_grp():
    """Session state, undo and redo (project snapshots)."""


@session_grp.command("status")
@click.pass_obj
@handle_error
def session_status(app: App):
    out(app, app.session.status())


@session_grp.command("undo")
@click.pass_obj
@handle_error
def session_undo(app: App):
    r = app.session.undo()
    app.reload_engine()
    out(app, r, "undone")


@session_grp.command("redo")
@click.pass_obj
@handle_error
def session_redo(app: App):
    r = app.session.redo()
    app.reload_engine()
    out(app, r, "redone")


@session_grp.command("history")
@click.option("--last", type=int, default=20)
@click.pass_obj
@handle_error
def session_history(app: App, last):
    out(app, app.session.data.get("history", [])[-last:])


# ── the motion workflow: plan, shelf, custom pieces, library, ratchet ───
# These commands need no engine. Files live in the user's studio (episodes/<id>/, brand/), never in the app.

def _exit(code: int) -> None:
    click.get_current_context().exit(code)


@cli.command("plan")
@click.argument("episode")
@click.option("--short", is_flag=True, help="The short form for a Short (format portrait, cap $0.50).")
@click.option("--check", "check_", is_flag=True,
              help="Validate the newest plan (or --file), compute density and budget, write the Markdown.")
@click.option("--file", "file_", default=None, help="edit/motion-plan-vNNN.json to check (default: the newest).")
@click.option("--card", is_flag=True, help="Check, then open the motion-plan card (one per video).")
@click.pass_obj
@handle_error
def plan_cmd(app: App, episode, short, check_, file_, card):
    """The motion pass: a plan skeleton from the words and the Writer's marks, or --check / --card a finished one."""
    from .. import paths
    from . import director as dr
    from . import library as lib
    if not check_ and not card:
        p = dr.skeleton(episode, short=short or None)
        plan = dr.load(p)
        ep_dir = paths.episode_dir(episode)
        rel = p.relative_to(ep_dir).as_posix()
        shelf = lib.entries(include_episodes=False)
        human = [f"{rel}: {len(plan['beats'])} beats, {len(plan['marks'])} Writer mark(s), cap ${plan['cap_usd']:g}.",
                 f"bar: {(plan.get('bar') or {}).get('episode') or 'none yet'} · lessons: {len(plan['lessons'])} · "
                 f"references: {len(plan['references'])}",
                 "Per beat: purpose, picture, column (a, b, c, or - for none; most beats get none). Then "
                 f"`crewcut motion plan {episode} --check --card`.", "shelf:"]
        human += [f"  {lib.line(r)}" for r in shelf] or ["  empty"]
        out(app, {"plan": rel, "md": dr.md_of(p).relative_to(ep_dir).as_posix(), "beats": len(plan["beats"]),
                  "marks": plan["marks"], "shelf": plan["shelf"]}, "\n".join(human))
        return
    ep_dir = paths.episode_dir(episode)
    p, errors, warns = dr.run_check(episode, ep_dir / file_ if file_ else None)
    plan = dr.load(p)
    data = {"plan": p.relative_to(ep_dir).as_posix(), "errors": errors, "warnings": warns,
            "density": plan["density"]["line"], "budget": plan["budget"]["line"]}
    if card and not errors:
        c = dr.propose_card(episode, p)
        data["card"] = c["id"]
    human = [f"{data['plan']}: {len(errors)} error(s), {len(warns)} warning(s)",
             f"  {data['density']} · {data['budget']}"]
    human += [f"  error: {e}" for e in errors] + [f"  warning: {w}" for w in warns]
    if data.get("card"):
        human.append(f"card #{data['card']} is open: motion plan v{int(plan['version']):03d}")
    out(app, data, "\n".join(human))
    if errors:
        _exit(1)


@cli.command("library")
@click.option("--no-episodes", is_flag=True, help="Only the app's and your pack's templates.")
@click.pass_obj
@handle_error
def library_cmd(app: App, no_episodes):
    """The shelf: the app's templates, your pack's own, and the custom pieces of your episodes."""
    from . import library as lib
    rows = lib.entries(include_episodes=not no_episodes)
    out(app, rows, "\n".join(lib.line(r) for r in rows) or "the shelf is empty")


@cli.command("new")
@click.argument("episode")
@click.argument("insert_id")
@click.option("--from", "brief", required=True, help="The brief: sentence(s), what must be understood in 2 s, "
              "format(s), length.")
@click.pass_obj
@handle_error
def new_cmd(app: App, episode, insert_id, brief):
    """A custom motion piece for this video: motion/<insert-id>/ with brief, beat sheet and a comp skeleton."""
    from . import custom
    d = custom.new(episode, insert_id, brief)
    out(app, {"folder": str(d), "comp": str(d / "comp.jsx"), "source": f"motion/{insert_id}/comp.jsx"},
        f"motion/{insert_id}/: brief.md, beats.md, refs/, review/, notes.md, comp.jsx (the ground and a slow push, "
        f"landscape and portrait). Plan source: motion/{insert_id}/comp.jsx. Next: one real frame, then "
        f"`crewcut motion style-frame {episode} {insert_id} --ours <frame>`.")


@cli.command("style-frame")
@click.argument("episode")
@click.argument("insert_id")
@click.option("--ours", multiple=True, required=True, help="Our frame (one per format; repeat for both).")
@click.option("--ref", multiple=True, help="The reference frame (else refs/, else the bar's frames).")
@click.option("--natural", is_flag=True, help="Grass, sky or footage: the one-hue limit does not apply.")
@click.pass_obj
@handle_error
def style_frame_cmd(app: App, episode, insert_id, ours, ref, natural):
    """Open the style-frame card: our frame next to the reference. Nothing animated is built before its yes."""
    from .. import approvals
    from . import custom
    c = custom.style_frame(episode, insert_id, list(ours), list(ref), natural=natural)
    out(app, approvals.view(c), f"card #{c['id']} is open: {c['title']}")


def _sample_renderer():
    """The render path's sample renderer, when it has one (``crewcut.render.motion.render_sample``)."""
    try:
        from ..render import motion as rmotion
    except ImportError:
        return None
    return getattr(rmotion, "render_sample", None)


@cli.command("promote")
@click.argument("episode")
@click.argument("insert_id")
@click.option("--name", required=True, help="The template name: lower case, digits and _.")
@click.option("--title", default=None, help="A short title for the shelf.")
@click.pass_obj
@handle_error
def promote_cmd(app: App, episode, insert_id, name, title):
    """Turn a reviewed custom piece (0 errors) into a template of your pack, then ask with a template card."""
    from . import library as lib
    e = lib.promote(episode, insert_id, name, _sample_renderer(), title=title)
    out(app, e, f"{name} v{e['version']} is in your pack (brand/templates/motion/{name}.jsx), waiting for your yes "
        f"on card #{e.get('card')}.")


@cli.command("report")
@click.argument("episode")
@click.option("--from", "from_", default=None, help="The Critic's filled form (JSON).")
@click.option("--skeleton", is_flag=True, help="Write the form to fill: review/motion-report-input.json.")
@click.pass_obj
@handle_error
def report_cmd(app: App, episode, from_, skeleton):
    """The motion report of a finished video against the bar; appends the lessons (at least one)."""
    from .. import paths
    from . import ratchet
    ep_dir = paths.episode_dir(episode)
    if skeleton or not from_:
        p = ep_dir / "review" / "motion-report-input.json"
        if p.exists():
            out(app, {"form": str(p)}, f"review/{p.name} exists already; fill it, then --from review/{p.name}")
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(ratchet.skeleton(episode), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        out(app, {"form": str(p)}, f"review/{p.name}: fill it (better, behind, upgrades, lessons with evidence), "
            f"then `crewcut motion report {episode} --from review/{p.name}`.")
        return
    src = ep_dir / from_ if not os.path.isabs(from_) and (ep_dir / from_).is_file() else from_
    data = parse_json_opt(f"@{src}", "--from")
    r = ratchet.report(episode, data if isinstance(data, dict) else {})
    human = [f"{r['file']}: {r['verdict_text']}", f"  better: {r['summary']['better']}",
             f"  behind: {r['summary']['behind']}", f"  next:   {r['summary']['next']}",
             "  lessons: " + ", ".join(x["id"] for x in r["lessons"])]
    if r.get("baseline_card"):
        human.append(f"card #{r['baseline_card']} asks whether this video becomes the bar")
    out(app, r, "\n".join(human))


@cli.command("lessons")
@click.pass_obj
@handle_error
def lessons_cmd(app: App):
    """The channel's motion lessons (brand/rules/motion.md) and the bar."""
    from . import lessons as ls
    from . import ratchet
    b = ratchet.bar()
    rows = ls.read()
    human = [f"bar: {b['episode']} (since {b.get('since')})" if b else "bar: none yet (the first approved video)"]
    human += [f"  {x['id'] or '-'}  {x['rule']}" for x in rows] or ["  no lessons yet"]
    if ls.needs_merge():
        human.append(f"  {len(rows)} lessons: above {ls.MERGE_ABOVE}, the Critic proposes a merge")
    out(app, {"bar": b, "lessons": rows}, "\n".join(human))


@cli.group("reference")
def reference_grp():
    """Motion references: reels and videos to learn timing and look from (they stay on this computer)."""


@reference_grp.command("add")
@click.argument("source")
@click.option("--reason", required=True, help="What to learn from it (the user's own sentence when they sent it).")
@click.option("--by", type=click.Choice(["user", "scout"]), default="user")
@click.option("--episode", default=None, help="The episode it was found for (the Scout: required).")
@click.option("--tag", "tags", multiple=True)
@click.option("--no-download", is_flag=True, help="Keep only the link.")
@click.pass_obj
@handle_error
def reference_add(app: App, source, reason, by, episode, tags, no_download):
    """File a link or a local clip or still."""
    from . import references as rf
    e = rf.add(source, reason, by=by, episode=episode or os.environ.get("CREWCUT_EPISODE") or None, tags=list(tags),
               download=None if no_download else rf.default_download)
    out(app, e, f"{e['id']}: {e.get('link') or e.get('file')} ({'file kept here' if e.get('file') else 'link only'})")


@reference_grp.command("from-chat")
@click.option("--episode", default=None)
@click.option("--text", required=True, help="The user's message with the link(s).")
@click.pass_obj
@handle_error
def reference_from_chat(app: App, episode, text):
    """The Showrunner files what the user dropped in the chat: each link, with the user's sentence as the reason."""
    from . import references as rf
    rows = rf.from_message(episode or os.environ.get("CREWCUT_EPISODE") or None, text)
    out(app, rows, "\n".join(f"{e['id']}: {e['link']} - {e['reason']}" for e in rows) or "no link in the message")


@reference_grp.command("list")
@click.pass_obj
@handle_error
def reference_list(app: App):
    from . import references as rf
    rows = rf.read()
    out(app, rows, "\n".join(f"{e['id']}  {e.get('by'):<5} {e.get('link') or e.get('file')}  {e.get('reason')}"
                             for e in rows) or "no references yet")


def main(argv: list[str] | None = None) -> int:
    """Run ``crewcut motion`` with ``argv`` (the words after ``motion``) and return the exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["--help"]
    # allow --json / --dry-run / --gpu anywhere on the line (agents often append them)
    for flag in ("--json", "--dry-run", "--gpu"):
        if flag in argv[1:] and argv.index(flag) > 0:
            argv.remove(flag)
            argv.insert(0, flag)
    try:
        rv = cli.main(args=argv, prog_name="crewcut motion", standalone_mode=False)
    except click.ClickException as e:
        e.show()
        return e.exit_code
    except click.exceptions.Abort:
        return 1
    return rv if isinstance(rv, int) else 0


if __name__ == "__main__":
    sys.exit(main())
