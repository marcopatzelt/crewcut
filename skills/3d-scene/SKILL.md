---
name: 3d-scene
description: "Builds 3D inserts by code in Blender, in the stage and colours of the style pack: one object with an action and one word, rendered locally on the CPU or on rented GPUs after a cost card. Use for: 3D scene, 3D insert, 3D b-roll, Blender scene, clay look, 3D object, probe frame, render on a GPU, new 3D template, measure a render."
---

# 3D scene

A 3D insert is one object that does something, one word, a calm camera move, on the stage of the style pack. Blender
builds it from code; nobody opens the Blender window. The look comes from `brand.json` (`stage3d`: background, material,
base colour, accent, font, samples, light) and from `brand/references/`. This skill holds the method only.

## The parts (do not reinvent them)

- `templates/3d/stage.py`: the shared kit. Stage (a curved backdrop), lights, materials from the pack, basic shapes,
  a flat word with an entrance, `render()`. Data keys and the list of scenes: `templates/3d/README.md`.
- Scene templates in `templates/3d/<scene>.py` (`object-word`, `row`, `grid3d`, `stack`, `slide`, `box`, `scale`). The
  neutral pack ships these few general scenes. A user's own scenes and models live in `brand/templates/3d/`.
- The edit plan places them (`"kind": "3d", "scene": "stack"`); `crewcut render probe|3d` renders them (skill `edit`).
- `python3 skills/3d-scene/scripts/measure_frame.py FRAME.png`: measures a rendered frame against `stage3d` and
  `stage3d.checks` of the pack.

## Order

1. **One picture with an action per sentence.** A card that swallows coins, sheets that fall into a stack, a box that
   opens. Never an object that only stands there. No pedestal.
2. **Cost first.** Count the frames of all 3D inserts. `crewcut compute estimate --kind blender --frames N` prints local
   and rented time and money. Rented costs money: card with the amount (`crewcut card propose --kind spend …`), then
   `crewcut card wait`. Only an identity with `may_spend: true` rents.
3. **Still frames at half size first:** `crewcut render probe <plan> <id>[,<id>…]`. Several scenes on one machine in one
   go. Look at each frame, measure it with `measure_frame.py`, put it next to the reference (a frame of
   `brand/references/` or of the baseline video) and judge honestly. Reject when the object fills too little of the frame
   (`stage3d.checks.object_height_min`), a shape sits in front of the object, the word touches the object or the edge,
   nothing happens before the cue, or the picture does not read in 2 seconds.
4. **Then the animation.** Local (`crewcut render 3d <plan> --local`): the container's CPU, slow, fine for a few
   seconds of 3D. Rented (`--rented --gpus N`): the workbench splits the frames into small packages, gives hanging
   packages to another machine and fetches frames as they come.
5. **After every rented job:** `crewcut compute destroy --all-ours` and show that no machine of ours runs. Also after a
   failure.
6. **Cut on the word:** the word in the picture lands 0 to 3 frames before it is spoken (the cues in the plan do that).

## Rules for the frame

- The object is large: at least `stage3d.checks.object_height_min` of the frame height.
- Action from frame 0, not only after the word.
- Small shapes at several depths, never in front of the object; the front ones may be soft and cut by the edge.
- One slow camera move per scene.
- Word beside the object, at most `stage3d.checks.word_height_max` of the frame height, flat, sharp, fully in the frame,
  in the font from `stage3d.font` (else the display font).
- Colours only from the pack. Not everything in the accent colour; real materials where they help.
- Colour management "Standard" when brand colours must stay exact (other view transforms make the accent pale; the
  measure script shows it as a large accent distance).

## Traps (Blender by code)

- A box made by a helper can have its pivot at the world origin. Parts that rotate hang on an empty object.
- Two text surfaces in the same place flicker. Move the hidden one out of the frame.
- Things that fall into a hole must not be visible through an opening next to it.
- Seen from above at an angle: put the word in front of the focus plane, or its lower line sinks into the floor.
- Short words grow huge at a fixed width: cap the word height.
- Figures (people, robots) built from basic shapes look cheap. Objects with an action carry the idea, or a real model.
- Long commands with Blender inline are fragile: write the scene to a file and run the file.
- Never send footage, keys or private data to a rented machine. Only scene code and fonts.

## Honest limits

- The measure script checks pack ranges, not taste. A frame that passes can still look empty or cheap.
- 3D is the most expensive part to adapt to a new brand. Colours and the font go through tokens; own models and an
  own stage are work per user.
- Nobody here has seen a frame of the neutral scenes yet (written 16 Nov 2026, untested).

## Planned

- Real models from an image (image to 3D) for the user's own objects, stored in `brand/templates/3d/models/`.
- Simple rigged figures with a licensed skeleton.
- One long camera move with a reveal per video.
- A comparison sheet (probe frame next to the reference) as one command.

## Sources

No connection to or endorsement by this channel; we took inspiration, not values.

- fern (YouTube channel), https://www.youtube.com/@fern-tv: inspiration for the 3D clay look only. No colours, sizes,
  timings or measurements from it are in Crewcut.
