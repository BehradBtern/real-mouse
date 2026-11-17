"""Live application loop.

    python -m virtual_mouse.app --mode absolute --camera 0

Hotkeys (focus the preview window):
    q / Esc  quit        c  switch camera      r  recalibrate     m  mirror
    p        pause       +/-  gain             1/2/3  presets
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace

from . import hud
from .config import Config
from .pipeline import Pipeline, make_smoother
from .tracking import HandTracker, TrackerUnavailable


PRESETS: dict[str, dict] = {
    # heavy smoothing: steadier for cheap webcams, slightly laggy on flicks
    "precise": dict(min_cutoff=0.8, beta=0.25, deadband_px=0.55, relative_gain=1.9),
    # the default: direct on flicks, calm at rest
    "balanced": dict(min_cutoff=1.0, beta=0.35, deadband_px=0.4, relative_gain=2.2),
    # minimal smoothing for a good camera and a steady hand
    "fast": dict(min_cutoff=2.0, beta=0.7, deadband_px=0.2, relative_gain=2.7),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="virtual-mouse",
        description="Webcam hand tracking that drives the real pointer.",
    )
    parser.add_argument("--camera", type=int, default=None, help="camera index (default 0)")
    parser.add_argument("--list-cameras", action="store_true", help="probe and print the working cameras, then exit")
    parser.add_argument("--mode", choices=["absolute", "relative"], default=None, help="pointer mapping")
    parser.add_argument("--gain", type=float, default=None, help="relative mode gain")
    parser.add_argument("--gamma", type=float, default=None, help="edge gain curve (1.0 = linear)")
    parser.add_argument("--smoothing", choices=sorted(PRESETS), default=None, help="feel preset")
    parser.add_argument("--no-preview", action="store_true", help="run without the preview window")
    parser.add_argument("--no-landmarks", action="store_true", help="hide the hand skeleton")
    parser.add_argument("--dry-run", action="store_true", help="never move the real pointer")
    parser.add_argument("--no-failsafe", action="store_true", help="disable the corner failsafe")
    parser.add_argument("--list-presets", action="store_true", help="print the presets and exit")
    return parser


def config_from_args(args: argparse.Namespace, base: Config | None = None) -> Config:
    config = base or Config()
    overrides = {
        "camera_index": args.camera,
        "mode": args.mode,
        "relative_gain": args.gain,
        "edge_gamma": args.gamma,
        "show_preview": False if args.no_preview else None,
        "draw_landmarks": False if args.no_landmarks else None,
        "dry_run": True if args.dry_run else None,
        "failsafe": False if args.no_failsafe else None,
    }
    config = config.with_overrides(**overrides)
    if args.smoothing:
        config = config.with_overrides(**PRESETS[args.smoothing])
    return config


def run(config: Config) -> int:
    try:
        tracker = HandTracker(config)
    except TrackerUnavailable as exc:
        print(f"error: {exc}")
        return 2

    pipeline = Pipeline(config)
    paused = False
    fps = 0.0
    last = time.perf_counter()

    print("virtual-mouse running — press q in the preview to quit")
    print(f"  mode={config.mode}  region={config.region}  smoothing={config.min_cutoff}/{config.beta}")

    try:
        while True:
            frame, hand, raw = tracker.read()
            if frame is None:
                print("error: the camera stopped returning frames")
                return 3

            now_ms = time.perf_counter() * 1000.0
            if paused:
                intent = pipeline.gestures.update(None, now_ms)
            else:
                intent = pipeline.step(hand, now_ms)

            position = pipeline.mouse.last_position or (
                pipeline.mouse.width // 2,
                pipeline.mouse.height // 2,
            )

            instant = 1.0 / max(1e-6, time.perf_counter() - last)
            last = time.perf_counter()
            fps = instant if fps == 0 else fps * 0.9 + instant * 0.1

            if config.show_preview:
                tracker.annotate(frame, raw)
                hud.draw(
                    tracker.cv2,
                    frame,
                    config,
                    intent,
                    position,
                    fps,
                    paused,
                    camera=tracker.index,
                    notice=tracker.active_notice(),
                )
                tracker.cv2.imshow("Real Mouse — virtual pointer", frame)

                key = tracker.cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key == ord("c"):
                    new_index = tracker.cycle_camera()
                    if new_index is not None:
                        config = replace(config, camera_index=new_index)
                        pipeline.config = config
                        print(f"camera={new_index}")
                if key == ord("r"):
                    pipeline.reset()
                    print("recalibrated")
                if key == ord("p"):
                    paused = not paused
                if key == ord("m"):
                    config = replace(config, mirror=not config.mirror)
                    tracker.config = config
                    pipeline.config = config
                    print(f"mirror={config.mirror}")
                if key in (ord("+"), ord("=")):
                    gain = min(6.0, config.relative_gain + 0.1)
                    config = replace(config, relative_gain=gain)
                    pipeline.config = config
                    print(f"gain={gain:.2f}")
                if key in (ord("-"), ord("_")):
                    gain = max(0.4, config.relative_gain - 0.1)
                    config = replace(config, relative_gain=gain)
                    pipeline.config = config
                    print(f"gain={gain:.2f}")
                if key in (ord("1"), ord("2"), ord("3")):
                    name = {ord("1"): "precise", ord("2"): "balanced", ord("3"): "fast"}[key]
                    config = replace(config, **PRESETS[name])
                    pipeline.config = config
                    pipeline.smoother = make_smoother(config)
                    pipeline.deadband.threshold = config.deadband_px
                    print(f"preset={name}")
            else:
                time.sleep(max(0.0, 1.0 / config.target_fps - (time.perf_counter() - last)))

    except KeyboardInterrupt:
        pass
    finally:
        pipeline.mouse.close()
        tracker.close()

    print(
        f"stopped — moves={pipeline.mouse.moves} clicks={pipeline.mouse.clicks} "
        f"scroll={pipeline.mouse.scroll_notches}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_presets:
        for name, values in PRESETS.items():
            print(f"{name:9s} {values}")
        return 0

    if args.list_cameras:
        config = config_from_args(args)
        try:
            tracker = HandTracker(config)
        except TrackerUnavailable as exc:
            print(f"error: {exc}")
            return 2
        tracker.release_camera()
        found = tracker.detect_cameras()
        tracker.close()
        print("cameras:", ", ".join(str(i) for i in found) if found else "none")
        return 0

    return run(config_from_args(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
