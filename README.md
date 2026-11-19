# Real Mouse — webcam hand tracking that behaves like a pointer

This is the project from that single-file script, rebuilt as a pointer engine you can
actually use: camera in, real cursor out. No magic, no cloud, no model downloads beyond
MediaPipe's bundled hand model.

```
landmarks → gesture engine → mapper → One-Euro filter → deadband → sub-pixel → OS pointer
```

The original `virtual_mouse.py` moved the cursor, but it did not *feel* like a mouse.
Six things were wrong, and each one is addressed by a specific piece of this code:

| Symptom in the old script | Cause | Fix here |
| --- | --- | --- |
| Cursor trembles while your hand is still | `prev + (target - prev) / 5` never converges | One-Euro filter + 0.4px deadband + sub-pixel accumulation |
| Fast moves lag behind your finger | fixed smoothing constant | filter cutoff rises with speed (`beta`) |
| Every pinch drags the cursor ~480px | the index *tip* moves towards the thumb | pinch-invariant anchor (index knuckle + first joint) |
| One pinch fires 3–6 clicks | a bare `distance < 0.04` threshold | hand-size normalization + Schmitt trigger + stable frames + release guard |
| Making a fist clicks first, scrolls second | fist check ran after the click branch | fist takes priority; clicks are suppressed from the first closed frame |
| Holding a pinch dragged the cursor | pinch held the left button down | clicks are atomic and latched: one pinch = one click, never a drag |
| A sideways fist stopped scrolling | fist tested with screen-space `tip.y > pip.y` | fist tested by fingertip distance to the wrist (rotation-invariant) |
| Losing your hand leaves the mouse button down | no state machine | 320ms hold, then a forced release |

## Install

```bash
python -m pip install -r requirements.txt
python scripts/run.py
```

`mediapipe` publishes wheels for CPython 3.9–3.12. On 3.13+ install into 3.12 and run with it:

```bash
py -3.12 -m pip install -r requirements.txt
py -3.12 scripts/run.py
```

Run without touching the real pointer (safe demo):

```bash
python scripts/run.py --dry-run
```

## Gestures

| Gesture | Action |
| --- | --- |
| Move your hand inside the box | pointer follows |
| Index + thumb pinch | left click (one pinch = one click, no drag mode) |
| Middle + thumb pinch, index extended | right click (350ms cooldown) |
| Closed fist + move up/down | scroll with momentum |
| Open your hand / leave the frame | nothing is held, nothing sticks |

Hotkeys in the preview: `q` quit · `c` switch camera · `r` recalibrate · `m` mirror · `p` pause ·
`[` / `]` deadband · `1` precise · `2` balanced · `3` fast. Add `--debug` to log detection
rate, coast rate and how often your hand leaves the active box every two seconds.

See which cameras actually work (probes indices 0–4 and reports the ones that
deliver frames):

```bash
python scripts/run.py --list-cameras
# cameras: 0, 1, 2
```

`c` cycles through them live — 0 → 1 → 2 → 0. The first press takes a moment
because the tracker has to release the device before it can probe; after that the
list is cached. The status panel always shows the camera in use (`cam1`).

## Modes

- **absolute** (default) — the cursor is where your hand is inside the active box. Predictable,
  and the edge curve (`edge_gamma=0.82`) adds gain near the borders so corners are reachable.
- **relative** — the cursor moves by hand delta × `relative_gain`, like an air trackpad.
  Steadier on noisy webcams and unlimited reach: `--mode relative --gain 2.2`.

## Tuning

Everything lives in `virtual_mouse/config.py` and can be overridden from the CLI.

| Field | Default | What it changes |
| --- | --- | --- |
| `region_*` | 0.18 / 0.82 / 0.16 / 0.84 | the active box inside the camera frame |
| `edge_gamma` | 0.82 | border gain; 1.0 = linear mapping |
| `min_cutoff` | 1.0 | filter base frequency — lower is smoother and laggier |
| `beta` | 0.35 | how fast the filter opens up with speed (0..1 dial) |
| `deadband_px` | 0.40 | movement below this is discarded |
| `pinch_press` / `pinch_release` | 0.50 / 0.72 | click hysteresis, normalized by hand size |
| `right_pinch_press` / `right_pinch_release` | 0.45 / 0.65 | middle-finger pinch for the right button |
| `stable_frames` | 1 | frames a pinch must hold before it counts |
| `click_guard_ms` | 150 | ignore a second click right after one fires |
| `scroll_gain` | 60.0 | notches per frame-height of wrist travel |
| `scroll_momentum` | 0.86 | wheel inertia after the fist opens |
| `relative_gain` | 2.2 | relative-mode sensitivity |

The presets (`precise`, `balanced`, `fast`) are just bundles of these numbers.

## Verify it

No camera needed for either of these.

```bash
python scripts/test.py          # 67 unit + pipeline tests, stdlib only
python scripts/simulate.py --json docs/simulation.json --svg docs/simulation-path.svg
```

The simulator runs the *production* pipeline over a scripted hand with camera-like noise
(circle → 3 clicks → right click → drag → fist scroll) and reports measured numbers:

```json
{
  "frames": 310,
  "duration_s": 5.17,
  "moves": 232,
  "left_clicks": 4,
  "held_buttons": 0,
  "right_clicks": 1,
  "scroll_notches": 21,
  "raw_jitter_px": 21.241,
  "cursor_jitter_px": 13.98,
  "jitter_reduction_pct": 34.2,
  "max_frame_jump_px": 198.1,
  "path_length_px": 5826.0
}
```

- 3 deliberate clicks + one deliberately long pinch → **4** left clicks and **0** held
  buttons: a pinch can never become a drag.
- 1 middle pinch → exactly **1** right click.
- 1 fist sweep → **21** scroll notches, no clicks.
- Jitter (mean absolute second difference of the cursor path) drops **34.2%**.
- Largest single-frame pointer step: 198.1px — the fastest scripted phase transition, not a
  filter artefact. `docs/simulation-path.svg` plots raw vs filtered.

The test that matters most is the one that caught the real bug:

```
test_cursor_is_smoother_than_the_raw_mapping ... ok
test_fist_enters_scroll_and_suppresses_clicks ... ok
test_hand_loss_never_leaves_the_button_down   ... ok
```

67 tests in total; `scripts/test.py` exits non-zero on the first failure.

## Layout

```
virtual_mouse/
  config.py     every tunable constant
  cameras.py    which camera comes next (pure, testable)
  filters.py    One-Euro, Schmitt trigger, deadband, sub-pixel accumulator
  gestures.py   landmark → gesture state machine
  mapping.py    absolute / relative mapping, edge curve, clamping
  actions.py    pyautogui backend + a recording backend for tests
  pipeline.py   the exact chain the app runs
  tracking.py   camera + MediaPipe, including live camera switching
  hud.py        on-camera overlay
  app.py        loop, CLI, hotkeys
scripts/        run.py · test.py · simulate.py
tests/          67 tests, no hardware required
docs/           simulation.json (add --svg to generate the path plot)
```

## Limits

- One hand, palm-facing the camera; MediaPipe needs decent light. Backlit rooms fail.
- Absolute mode cannot reach a corner if your arm cannot, that is why relative mode exists.
- 60fps tracking needs a 720p webcam; the lite model (`model_complexity=0`) is the default.
- Windows/macOS/Linux all work through `pyautogui`; Wayland needs XWayland.
- `pyautogui.FAILSAFE` is on: slam the pointer into a screen corner to abort.

## Rollback

The runtime is stateless. To revert a bad change:

```bash
git revert <commit>          # or: git checkout <tag> -- .
```

If a pointer gets stuck, press `q` (the app releases the button on exit) or hit the
failsafe corner. `--dry-run` proves the pipeline without touching the OS at all.

## License

MIT © 2026 Behrad
