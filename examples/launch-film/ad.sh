#!/bin/bash
# The launch film as one EffectCraft project with a global timeline (comp Master), built only through `crewcut motion`.
#   bash ad.sh [stages]   stages: comma list of world,beat2,beat3,beat4,beat5,beat6,beat7,master (default all)
#   PROJECT=$WORK/p/test.ecproj bash ad.sh beat4,beat5      # build a few beats into a test project
# Global times: beat 2 0-2.7 (click T0 0.92), beat 3 2.7-6.85 (meadow, push into the bar, typing, pull back, click),
# beat 4 6.85-10.05, beat 5 10.05-12.25, beat 6 12.25-15.05, beat 7 15.05-17.5.
# Needs: the plates in $OUT (plates.sh), the prepared assets in $ASSETS (prep.sh), the templates in ./templates.
# Delete a test project before rebuilding it: running a stage again on an existing project adds a second comp.
set -e
. "$(dirname "$0")/env.sh"
STAGES=${1:-world,beat2,beat3,beat4,beat5,beat6,beat7,master}
has(){ [[ ",$STAGES," == *",$1,"* ]] || [[ "$STAGES" == all ]]; }
A=$ASSETS; O=$OUT; LOG=$WORK/ad.log
mkdir -p "$(dirname "$PROJECT")"
# a failed step prints the call and the end of its JSON error, then stops (inside set -e it would die silently)
ok(){ "$@" >"$LOG" 2>&1 || { echo "FAILED: $*" | cut -c1-300; tail -c 1500 "$LOG"; exit 1; }; }
if [ ! -f "$PROJECT" ] || has world; then
  ok crewcut motion project new -o "$PROJECT" --comp Master --duration 17.5 --bg '#F2F1EE' --samples 16 --overwrite
fi
E="crewcut motion --json --project $PROJECT --templates-dir $HERE/templates"

# ── World (global time): meadow (Blender, HDRI sky) + bloom, frosted bar with push-in and typing ──────────
if has world; then
  ok $E comp new Backdrop --duration 7.2 --no-use --bg '#7FB8E8'
  ok $E layer add footage --comp Backdrop --path $O/meadow/meadow_0001.jpg --sequence --frame-rate 60 --name Meadow --pos 960,540 --scale 83.3333,83.3333
  ok $E exec layer.timing --params '{"comp":"Backdrop","layers":["Meadow"],"start":2.03}'
  ok $E effect apply Meadow glow --comp Backdrop --values '{"threshold": 86, "radius": 60, "intensity": 0.25}'
  # the camera never stops: slow push after the iris, push-in to the bar with blur, pull back
  ok $E key set Meadow transform/scale 2.3=83.3333,83.3333 3.5=86.5,86.5 4.4=93.3,93.3 5.55=93.3,93.3 6.25=86,86 6.9=87.5,87.5 --ease smooth --comp Backdrop
  ok $E effect apply Meadow "Gaussian Blur" --comp Backdrop --keys '{"blurriness": [[3.5, 0], [4.4, 12], [5.55, 12], [6.25, 0]]}' --ease smooth
  ok $E comp new World --duration 7.2 --no-use
  ok $E layer add precomp --comp World --source Backdrop --name Backdrop
  ok $E run-template glass_prompt_typing --params '{"comp":"World","backdrop":"Backdrop","center":[960,615],"size":[960,230],"fieldH":104,"textSize":42,
     "icon":"'$A'/icon-crewcut.png","slide":[[2.07,[760,790],0],[2.30,[960,620],100]],
     "pushKeys":[[2.3,100],[3.45,108],[4.4,320],[5.55,320],[6.25,100]],"pushEase":["linear","strong","linear","expo"],
     "clickAt":3.45,"text":"Make my next video","typeStart":3.95,"typeEnd":4.95}'
fi

# ── Beat 2 (0-2.7): dock -> click -> pixel wave + rings + 3D Slate -> bristles/swirl -> iris into World ──────
if has beat2; then
  ok $E comp new Beat2 --duration 2.7 --no-use --bg '#F2F1EE' --samples 16
  ok $E run-template app_dock --params '{"comp":"Beat2","center":[960,540],"size":134,"gap":29,"pad":26,"radius":46,
     "icons":["'$A'/icon-notes.png","'$A'/icon-chat.png","'$A'/icon-crewcut.png","'$A'/icon-folder.png","'$A'/icon-camera.png"],
     "hovers":[[4,0.36],[3,0.56]],"click":[2,0.92],"breakAt":0.99,"fadeOut":[1.02,1.12],"out":1.2}'
  ok $E run-template cursor_flyin --params '{"comp":"Beat2","path":[[0.05,2000,250],[0.36,1286,570],[0.56,1124,576],[0.80,972,568],[0.92,966,562]],"ease":"soft","clicks":[0.92],"height":60,"out":1.05}'
  ok $E layer add footage --comp Beat2 --path $O/pixelgrid/outline_0001.png --sequence --frame-rate 60 --name "Pixel outlines" --pos 960,540
  ok $E exec layer.timing --params '{"comp":"Beat2","layers":["Pixel outlines"],"start":0.97}'
  ok $E run-template burst_rings --params '{"comp":"Beat2","t":0.99,"center":[960,540],"dur":0.23,"stagger":0.02,"radii":[255,440,660,930,1300],
     "midLayer":{"path":"'$O'/pixelgrid/fill_0001.png","sequence":true,"frameRate":60,"start":0.97,"name":"Pixel fills"},
     "pushKeys":[[1.62,100],[1.96,118],[2.14,420]],"pushEase":["linear","expoIn"]}'
  ok $E run-template flash --params '{"comp":"Beat2","t":0.94,"center":[960,540],"size":220,"blur":60,"opacity":70,"frames":5,"name":"Click flash"}'
  ok $E run-template iris_reveal --params '{"comp":"Beat2","plateComp":"World","center":[960,540],"rimBlur":70,"rimOpacity":45}'
  ok $E run-template flash --params '{"comp":"Beat2","t":2.04,"center":[960,540],"size":500,"blur":120,"opacity":85,"frames":5,"name":"Iris flash"}'
  ok $E layer add footage --comp Beat2 --path $O/slate3d/slate_0001.png --sequence --frame-rate 60 --name "Slate 3D" --pos 960,540 --scale 95,95
  ok $E exec layer.timing --params '{"comp":"Beat2","layers":["Slate 3D"],"start":0.95}'
  ok $E key set "Slate 3D" transform/scale 1.62=95,95 1.96=112,112 2.22=142,142 --ease linear --comp Beat2
fi


# ── Beat 4 (local 0-3.2, global 6.85): hero card springs in, grid of cards in tilted 3D ─────────────────────
# The cards are $ASSETS/cards/*.png (prep.sh): your own images mixed with pastel crew cards, a crew card after every
# two of yours (pastel cards keep one hue from dominating). HERO picks the hero card (default: your first image).
if has beat4; then
  read -r HERO_JSON CARDS_JSON < <(python3 - "$A/cards" "${HERO:-}" <<'PY'
import json, sys
from pathlib import Path
d, hero = Path(sys.argv[1]), sys.argv[2]
crew = sorted(str(p) for p in d.glob("crew-*.png"))
own = sorted(str(p) for p in d.glob("*.png") if not p.name.startswith(("crew-", "_")))
if not crew and not own:
    sys.exit(f"no cards in {d}: run prep.sh first")
hero = hero or (own or crew)[0]
own, crew = [p for p in own if p != hero], [p for p in crew if p != hero]
cards, i, k = [], 0, 0
while len(cards) < 24 and (i < len(own) or k < len(crew)):
    for _ in range(2):
        if i < len(own):
            cards.append(own[i]); i += 1
    if k < len(crew):
        cards.append(crew[k]); k += 1
print(json.dumps(hero), json.dumps(cards[:24], separators=(",", ":")))
PY
  )
  [ -n "$CARDS_JSON" ] || exit 1
  ok $E comp new "Beat4 grid" --duration 3.2 --no-use --bg '#FBFBFA' --samples 16
  ok $E run-template card_grid_3d --params '{"comp":"Beat4 grid","hero":'"$HERO_JSON"',"cards":'"$CARDS_JSON"',"button":"Upload","buttonAt":1.9}'
  ok $E comp new Beat4 --duration 3.2 --no-use --bg '#FBFBFA' --samples 16
  ok $E layer add precomp --comp Beat4 --source "Beat4 grid" --name "Grid"
  ok $E run-template cursor_flyin --params '{"comp":"Beat4","path":[[1.45,2000,1000],[1.95,1100,420],[2.85,1100,420],[2.95,1100,420]],"ease":"expo","clicks":[2.92],"height":60,"in":1.45,"out":3.2,"name":"Cursor 4"}'
  # the cursor lands on the button wherever the 3D grid has put it (button position from the grid comp)
  ok $E expr set "Cursor 4" transform/position 'var b = comp("Beat4 grid").layer("Grid button").toComp([0, 0, 0]); var k = ease(time, 1.6, 1.95, 0, 1); var tgt = [b[0] + 10, b[1] + 12]; [value[0] * (1 - k) + tgt[0] * k, value[1] * (1 - k) + tgt[1] * k]' --comp Beat4
  ok $E layer add shape --comp Beat4 --kind ellipse --size 4600,4600 --fill '#0C0E12' --name "Wipe to dark" --in 2.95 --out 3.2 --mb
  ok $E expr set "Wipe to dark" transform/position 'thisComp.layer("Cursor 4").transform.position' --comp Beat4
  ok $E key set "Wipe to dark" transform/scale 2.95=0.5,0.5 3.2=100,100 --ease strong --comp Beat4
fi

# ── Beat 5 (local 0-2.2, global 10.05): word reel on dark, lands on "Upload", click ─────────────────────────
if has beat5; then
  ok $E comp new Beat5 --duration 2.2 --no-use --bg '#0C0E12' --samples 16
  ok $E run-template word_reel --params '{"comp":"Beat5","backdrop":"'$A'/reel-backdrop.png","t0":0.05,"t1":1.2}'
  ok $E run-template cursor_flyin --params '{"comp":"Beat5","path":[[1.25,1700,1020],[1.62,1010,566],[1.8,1004,560]],"ease":"expo","clicks":[1.8],"height":60,"in":1.25,"out":2.2,"name":"Cursor 5"}'
  ok $E layer add shape --comp Beat5 --kind ellipse --size 4600,4600 --fill '#F7F6F3' --name "Wipe to light" --pos 1004,560 --in 1.92 --out 2.2 --mb
  ok $E key set "Wipe to light" transform/scale 1.92=0.5,0.5 2.2=100,100 --ease strong --comp Beat5
fi


# ── Beat 6 (local 0-2.8, global 12.25): "Ship the" types, "Video!" smashes in (Blender type) with a splash ──
if has beat6; then
  ok $E comp new Beat6 --duration 2.8 --no-use --bg '#F7F6F3' --samples 16
  ok $E run-template type_smash_splash --params '{"comp":"Beat6","plate":"'$O'/type3d/type_0001.png","plateStart":0.0,"card":"'$A'/cards/crew-writer.png",
     "splashCenter":[1240,650],"cardPos":[1150,320]}'
  ok $E run-template cursor_flyin --params '{"comp":"Beat6","path":[[0.55,300,160],[0.78,640,250],[0.98,880,470]],"ease":"expo","clicks":[0.98],"height":60,"in":0.55,"out":1.1,"name":"Cursor 6"}'
  ok $E effect apply "Cursor 6" echo --comp Beat6 --values '{"echoTime": -0.012, "numberOfEchoes": 7, "startingIntensity": 0.8, "decay": 0.72}'
fi

# ── Beat 7 (local 0-2.45, global 15.05): green chips converge into Slate, then the lockup ──────────────────
if has beat7; then
  ok $E comp new Beat7 --duration 2.45 --no-use --bg '#FBFBFA' --samples 16
  ok $E run-template particles_converge --params '{"comp":"Beat7","plate":"'$O'/slate7r/conv_0001.png","plateFrames":94,"skip":24}'
fi

# ── Beat 3 (2.7-6.85) lives in World; the cursor and the exit wipe sit in Master ────────────────────────────
# ── Master ──────────────────────────────────────────────────────────────────────────────────────────────────
if has master; then
  ok $E layer add precomp --comp Master --source Beat2 --name "Beat 2" --out 2.7
  ok $E layer add precomp --comp Master --source World --name "Beat 3 world"
  ok $E layer timing "Beat 3 world" --in 2.69 --out 6.95 --comp Master
  # beat 3 cursor: into the field (click 3.45), away during the push; back to the search glyph (click 6.55)
  ok $E run-template cursor_flyin --params '{"comp":"Master","path":[[2.8,2050,960],[3.3,652,594],[3.45,646,590]],"ease":"expo","clicks":[3.45],"height":60,"in":2.8,"out":3.62,"name":"Cursor 3a"}'
  ok $E run-template cursor_flyin --params '{"comp":"Master","path":[[6.0,1820,1000],[6.45,1336,592],[6.55,1330,588]],"ease":"expo","clicks":[6.55],"height":60,"in":6.0,"out":6.7,"name":"Cursor 3b"}'
  # exit: a white circle grows from the search glyph and becomes beat 4's white ground
  ok $E layer add shape --comp Master --kind ellipse --size 4600,4600 --fill '#FBFBFA' --name "Wipe to white" --pos 1330,588 --in 6.6 --out 6.95 --mb
  ok $E key set "Wipe to white" transform/scale 6.6=0.5,0.5 6.85=100,100 --ease strong --comp Master
  if has beat4 || $E comp info --comp Beat4 >/dev/null 2>&1; then ok $E layer add precomp --comp Master --source Beat4 --name "Beat 4"; ok $E exec layer.timing --params '{"comp":"Master","layers":["Beat 4"],"start":6.85}'; fi
  if has beat6 || $E comp info --comp Beat6 >/dev/null 2>&1; then ok $E layer add precomp --comp Master --source Beat6 --name "Beat 6"; ok $E exec layer.timing --params '{"comp":"Master","layers":["Beat 6"],"start":12.25}'; fi
  if has beat7 || $E comp info --comp Beat7 >/dev/null 2>&1; then ok $E layer add precomp --comp Master --source Beat7 --name "Beat 7"; ok $E exec layer.timing --params '{"comp":"Master","layers":["Beat 7"],"start":15.05}'; fi
  if has beat5 || $E comp info --comp Beat5 >/dev/null 2>&1; then ok $E layer add precomp --comp Master --source Beat5 --name "Beat 5"; ok $E exec layer.timing --params '{"comp":"Master","layers":["Beat 5"],"start":10.05}'; fi
fi
echo "built $STAGES"
