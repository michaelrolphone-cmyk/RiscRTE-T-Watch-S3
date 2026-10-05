#!/usr/bin/env python3
"""Prove schedule-label glyph pixels and render real defaults at native 240x240.

Uses the production C renderer and the production Utilities defaults, encoded
records, and timezone-aware recurrence projection. Screenshots are host-rendered
RGB565 output, not HTML approximations or physical-watch captures.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("NEXT", "RING", "LADDER", "DAYLINE", "TRIPLE", "STATUS", "BOARD", "WORKDAY", "UP NEXT")
CASES = ("Wakeup next | Mon 2026-10-05 04:00 Denver",
         "Drive to Work next | Mon 2026-10-05 04:45 Denver",
         "Work End next | Mon 2026-10-05 16:15 Denver")


def legacy_fixture():
    """Copy shipped glyph records/alpha verbatim; only symbols are renamed."""
    parts = ["/* Test-only extraction of retained shipped font data. */"]
    for filename, glyph, font, alpha, prefix in (
            ("assets.inc", "fg_r10", "legacy_ff_r10", "face_alpha", "legacy_face_alpha"),
            ("points_assets.inc", "ps_g_r14", "legacy_ps_r14", "points_alpha", "legacy_points_alpha")):
        source = (ROOT / "apps/clock/faces" / filename).read_text()
        records = re.search(r"static const face_glyph " + glyph + r"\[\]=\{(.*?)\};", source, re.S)
        data = re.search(r"static const uint8_t " + alpha + r"\[\]=\{(.*?)\};", source, re.S)
        assert records and data, filename
        parts += [f"static const face_glyph {font}_glyphs[]={{" + records[1] + "};",
                  f"static const face_font {font}={{{font}_glyphs,COUNT({font}_glyphs)}};",
                  f"static const uint8_t {prefix}[]={{" + data[1] + "};"]
    return "\n".join(parts) + "\n"


def decode(path):
    raw = path.read_bytes()
    assert len(raw) == 240 * 240 * 2
    rgb = bytearray()
    for i in range(0, len(raw), 2):
        v = raw[i] | raw[i + 1] << 8
        rgb.extend(((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31))
    return Image.frombytes("RGB", (240, 240), bytes(rgb))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--system-apps", type=Path, default=ROOT.parent / "system-apps")
    p.add_argument("--utilities", type=Path, default=ROOT.parent / "utilities")
    p.add_argument("--output", type=Path, default=ROOT / "dist/points-label-pixels")
    args = p.parse_args()
    system, utilities, out = (x.resolve() for x in (args.system_apps, args.utilities, args.output))
    assert (system / "lib/PortableApps/include").is_dir(), system
    assert (utilities / "lib/Alarm/include/PointsRecords.h").is_file(), utilities
    out.mkdir(parents=True, exist_ok=True)
    (out / "points_label_legacy_fixture.inc").write_text(legacy_fixture())
    includes = [system / "lib/PortableApps/include", system / "lib/NativeApps/include",
                utilities / "lib/Alarm/include", ROOT, ROOT / "sdk/app", ROOT / "sdk/driver", ROOT / "include", out]
    flags = ["-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
             "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer", "-no-pie",
             "-DPORTABLE_RTC_UTC8_DENVER", *("-I" + str(x) for x in includes)]
    binary = out / "points-label-pixels-test"
    subprocess.run([os.environ.get("CC", "cc"), *flags, str(ROOT / "tests/points_label_pixels_test.c"),
                    str(ROOT / "apps/clock/points_projection.c"), "-o", str(binary)], check=True)
    subprocess.run([str(binary), str(out)], check=True, timeout=120)

    frame_names = [f"default-{case}-face-{face:02}" for case in range(3) for face in range(33)]
    frame_names += ["legacy-drive-collapsed", "current-drive-complete",
                    "legacy-wakeup-collapsed", "current-wakeup-complete"]
    hashes = {}
    for name in frame_names:
        path = out / (name + ".rgb565")
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        decode(path).save(path.with_suffix(".png"))
    for scenario, label in enumerate(CASES):
        # No resizing: each tile is the original native 240x240 pixel frame.
        sheet = Image.new("RGB", (768, 842), "#080b0d")
        draw = ImageDraw.Draw(sheet)
        draw.text((12, 8), "ACTUAL C RGB565 | PRODUCTION DEFAULTS | " + label, fill="white")
        for i, name in enumerate(NAMES):
            x, y = 8 + i % 3 * 256, 32 + i // 3 * 270
            sheet.paste(decode(out / f"default-{scenario}-face-{i + 24:02}.rgb565"), (x, y))
            draw.text((x + 78, y + 244), name, fill="white")
        sheet.save(out / f"default-{scenario}-schedule-sheet.png")
    comparison = Image.new("RGB", (512, 562), "#080b0d")
    draw = ImageDraw.Draw(comparison)
    for i, (filename, caption) in enumerate((
            ("legacy-drive-collapsed", "SHIPPED: Drive to Work -> D  W"),
            ("current-drive-complete", "FIXED: Drive to Work"),
            ("legacy-wakeup-collapsed", "SHIPPED: Wakeup -> W"),
            ("current-wakeup-complete", "FIXED: Wakeup"))):
        x, y = 8 + i % 2 * 256, 28 + i // 2 * 270
        comparison.paste(decode(out / (filename + ".rgb565")), (x, y))
        draw.text((x, y - 18), caption, fill="white")
    comparison.save(out / "legacy-current-comparison.png")
    (out / "frame-sha256.json").write_text(json.dumps(hashes, indent=2) + "\n")
    sources = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in [ROOT / "tests/points_label_pixels_test.c", Path(__file__).resolve(),
                            ROOT / "apps/clock/points_projection.c", ROOT / "apps/clock/nova/nova.c",
                            ROOT / "apps/clock/faces/points_state.h",
                            *(ROOT / "apps/clock/faces").glob("*.inc")]}
    for name in ("PointsRecords.h", "PointsSchedule.h"):
        path = utilities / "lib/Alarm/include" / name
        sources["Utilities/lib/Alarm/include/" + name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {"renderer": "production C RGB565, host-rendered, not a physical-watch capture",
                "dimensions": [240, 240], "face_count": 33, "scenario_count": 3,
                "scenarios": list(CASES), "frames": hashes, "source_sha256": sources,
                "sanitizers": ["address", "undefined"],
                "asan_options": os.environ.get("ASAN_OPTIONS", ""),
                "glyph_styles": 11, "printable_ascii_per_style": 95,
                "glyph_modes": ["native", "70-percent fitted"],
                "proof_files": ["glyph-pixels.tsv", "text-calls.tsv", "legacy-current-comparison.png"]}
    (out / "proof-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{len(hashes)} native 240x240 production frames; glyph pixels/text-call evidence; 3 schedule sheets: {out}")


if __name__ == "__main__":
    main()
