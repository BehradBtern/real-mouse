"""Headless simulation of a full session.

This exists because a webcam is not required to prove the engine works. It runs
the *real* pipeline (gestures -> mapping -> filter -> controller) over a scripted
hand with sensor noise, then reports:

  * how much jitter the filter removed,
  * how many clean clicks/drags/scroll notches came out of it,
  * the largest single-frame pointer jump.

    python scripts/simulate.py
    python scripts/simulate.py --json docs/simulation.json --svg docs/simulation-path.svg
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from virtual_mouse.actions import RecordingBackend  # noqa: E402
from virtual_mouse.config import Config  # noqa: E402
from virtual_mouse.mapping import Mapper  # noqa: E402
from virtual_mouse.pipeline import Pipeline, path_jitter  # noqa: E402

FRAME_MS = 1000.0 / 60.0
SCALE = 0.28


def hand(pinch: float = 1.0, fist: bool = False, x: float = 0.5, y: float = 0.5, middle: float = 1.0):
    """Build 21 normalized landmarks with a known pinch ratio (see tests/helpers)."""
    points = [(x, y)] * 21
    points[0] = (x, y + SCALE)          # wrist
    points[9] = (x, y)                  # middle knuckle -> hand scale anchor
    points[4] = (x, y)                  # thumb tip
    points[8] = (x + pinch * SCALE, y)  # index tip
    points[12] = (x + middle * SCALE, y + 0.015)

    if fist:
        for tip_idx, pip_idx, offset in ((8, 6, 0.02), (12, 10, 0.03), (16, 14, 0.04), (20, 18, 0.05)):
            points[pip_idx] = (x + 0.02, y - 0.02)
            points[tip_idx] = (x + 0.02, y + offset)
    else:
        for tip_idx, pip_idx, offset in ((16, 14, 0.12), (20, 18, 0.13)):
            points[pip_idx] = (x + 0.02, y + 0.03)
            points[tip_idx] = (points[pip_idx][0], points[pip_idx][1] - offset)
    from virtual_mouse.gestures import HandFrame  # local import keeps the module import-light

    return HandFrame(points=points)


def build_session(seed: int = 11):
    """Return [(hand, label), ...] describing a realistic, continuous run."""
    random.seed(seed)
    frames: list[tuple[object, str]] = []
    pos = [0.5, 0.5]

    def glide(target: tuple[float, float], steps: int, label: str = "move") -> None:
        """Move the hand smoothly, so the path has no scripted teleports."""
        start = tuple(pos)
        for i in range(1, steps + 1):
            t = i / steps
            x = start[0] + (target[0] - start[0]) * t
            y = start[1] + (target[1] - start[1]) * t
            pos[0], pos[1] = x, y
            frames.append((hand(x=x, y=y), label))

    # 1. tracking a circle, with the kind of noise a cheap webcam produces
    for i in range(120):
        angle = 2 * math.pi * i / 120
        x = 0.5 + 0.20 * math.cos(angle) + random.gauss(0, 0.005)
        y = 0.5 + 0.18 * math.sin(angle) + random.gauss(0, 0.005)
        pos[0], pos[1] = x, y
        frames.append((hand(x=x, y=y), "move"))

    glide((0.5, 0.5), 14)

    # 2. three deliberate clicks
    for _ in range(3):
        frames += [(hand(pinch=0.18, x=pos[0], y=pos[1]), "click")] * 6
        frames += [(hand(pinch=1.0, x=pos[0], y=pos[1]), "move")] * 12

    # 2b. one right click (middle finger pinches the thumb)
    frames += [(hand(pinch=1.0, middle=0.18, x=pos[0], y=pos[1]), "right")] * 6
    frames += [(hand(pinch=1.0, x=pos[0], y=pos[1]), "move")] * 12

    # 3. a drag across the middle of the screen
    glide((0.32, 0.55), 12)
    frames += [(hand(pinch=0.18, x=0.32, y=0.55), "drag")] * 6
    for i in range(36):
        pos[0], pos[1] = 0.32 + i * 0.01, 0.55
        frames.append((hand(pinch=0.18, x=pos[0], y=pos[1]), "drag"))
    frames += [(hand(pinch=1.0, x=pos[0], y=pos[1]), "move")] * 8

    # 4. fist scroll: the hand travels up, then opens
    for i in range(4):
        pos[1] = 0.6 - i * 0.004
        frames.append((hand(fist=True, x=pos[0], y=pos[1]), "scroll"))
    for i in range(30):
        pos[1] = 0.584 - i * 0.012
        frames.append((hand(fist=True, x=pos[0], y=pos[1]), "scroll"))
    frames += [(hand(fist=False, x=pos[0], y=pos[1]), "move")] * 8

    return frames


def simulate(frames, config: Config):
    backend = RecordingBackend()
    pipeline = Pipeline(config, backend)
    raw_mapper = Mapper(pipeline.mouse.width, pipeline.mouse.height, config)

    raw_path: list[tuple[float, float]] = []
    cursor_path: list[tuple[float, float]] = []
    labels: list[str] = []
    frame_index: list[int] = []

    now = 0.0
    for index, (hand_frame, label) in enumerate(frames):
        now += FRAME_MS
        pipeline.step(hand_frame, now)
        if hand_frame is not None and label != "scroll":
            u, v = hand_frame.anchor()
            raw_path.append(raw_mapper.map(u, v))
            cursor_path.append(pipeline.mouse.last_position or (0.0, 0.0))
            labels.append(label)
            frame_index.append(index)

    jumps = []
    for i in range(1, len(cursor_path)):
        # Only compare consecutive frames inside one phase: the synthetic hand
        # teleports between phases, which is not something a real hand does.
        if frame_index[i] - frame_index[i - 1] == 1 and labels[i] == labels[i - 1]:
            a, b = cursor_path[i - 1], cursor_path[i]
            jumps.append(math.hypot(b[0] - a[0], b[1] - a[1]))

    downs = backend.of_type("down")
    ups = backend.of_type("up")
    rights = [e for e in backend.of_type("click") if e[1] == "right"]
    scroll_values = [e[1] for e in backend.of_type("scroll")]

    # A drag is a press that accumulated real movement before it was released.
    drags = 0
    moves_since_press: list[tuple[int, int]] = []
    for event in backend.events:
        if event[0] == "move":
            moves_since_press.append((event[1], event[2]))
        elif event[0] == "down" and event[1] == "left":
            moves_since_press.clear()
        elif event[0] == "up" and event[1] == "left":
            if len(moves_since_press) >= 2:
                span = math.dist(moves_since_press[0], moves_since_press[-1])
                if span > 20:
                    drags += 1
            moves_since_press.clear()

    raw_jit = path_jitter(raw_path)
    cur_jit = path_jitter(cursor_path)

    return {
        "frames": len(frames),
        "duration_s": round(len(frames) * FRAME_MS / 1000.0, 2),
        "moves": len(backend.of_type("move")),
        "left_downs": len(downs),
        "left_ups": len(ups),
        "drags": drags,
        "right_clicks": len(rights),
        "scroll_notches": sum(abs(v) for v in scroll_values),
        "scroll_events": len(scroll_values),
        "raw_jitter_px": round(raw_jit, 3),
        "cursor_jitter_px": round(cur_jit, 3),
        "jitter_reduction_pct": round(100.0 * (1 - cur_jit / raw_jit), 1) if raw_jit else 0.0,
        "max_frame_jump_px": round(max(jumps) if jumps else 0.0, 1),
        "path_length_px": round(sum(jumps), 0),
        "final_position": pipeline.mouse.last_position,
        "raw_path": raw_path,
        "cursor_path": cursor_path,
    }


def to_svg(result: dict, width: int = 960, height: int = 540) -> str:
    sw, sh = 1920.0, 1080.0

    def project(point):
        return point[0] / sw * width, point[1] / sh * height

    raw = " ".join(f"{x:.1f},{y:.1f}" for x, y in (project(p) for p in result["raw_path"]))
    cur = " ".join(f"{x:.1f},{y:.1f}" for x, y in (project(p) for p in result["cursor_path"]))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="Simulated hand path versus filtered cursor path">
  <rect width="{width}" height="{height}" fill="#f4f2ed"/>
  <g stroke="#e2ded5" stroke-width="1">
    <path d="M0 {height/2} H{width} M{width/2} 0 V{height}"/>
  </g>
  <polyline points="{raw}" fill="none" stroke="#c9c3b8" stroke-width="1.2"/>
  <polyline points="{cur}" fill="none" stroke="#a8461c" stroke-width="1.6"/>
  <g font-family="ui-monospace, Consolas, monospace" font-size="11" fill="#6b6660">
    <text x="20" y="28">REAL MOUSE · simulated session</text>
    <text x="20" y="{height - 34}">raw landmark path — jitter {result['raw_jitter_px']} px</text>
    <rect x="20" y="{height - 26}" width="18" height="2" fill="#c9c3b8"/>
    <text x="20" y="{height - 12}">filtered cursor — jitter {result['cursor_jitter_px']} px ({result['jitter_reduction_pct']}% less)</text>
    <rect x="290" y="{height - 20}" width="18" height="2" fill="#a8461c"/>
    <text x="{width - 240}" y="28">{result['left_downs']} clicks · {result['drags']} drags · {result['scroll_notches']} notches</text>
  </g>
</svg>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the pointer pipeline without a camera.")
    parser.add_argument("--json", help="write the full metrics + paths to this file")
    parser.add_argument("--svg", help="write an SVG plot of raw vs filtered paths")
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()

    config = Config(dry_run=True)
    frames = build_session(args.seed)
    result = simulate(frames, config)

    printable = {k: v for k, v in result.items() if not k.endswith("_path")}
    print(json.dumps(printable, indent=2))

    if args.json:
        path = Path(args.json)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in result.items() if not k.endswith("_path")}
        payload["seed"] = args.seed
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}")

    if args.svg:
        path = Path(args.svg)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_svg(result), encoding="utf-8")
        print(f"wrote {path}")

    # A session that produced no clicks is a broken session, not a quiet one.
    ok = result["left_downs"] >= 3 and result["scroll_notches"] > 0 and result["cursor_jitter_px"] < result["raw_jitter_px"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
