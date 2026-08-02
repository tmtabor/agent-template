#!/usr/bin/env python3
"""Render an emoji to a macOS .iconset directory (all sizes Apple's iconutil expects).

Usage:
    uv run --with pillow python scripts/render_emoji_icon.py <emoji> <out.iconset>

Only needed for scripts/build_launcher.sh — not a runtime dependency of the
app itself, which is why this isn't in pyproject.toml and is invoked with
`uv run --with pillow` instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/System/Library/Fonts/Apple Color Emoji.ttc"

# (filename, pixel size) pairs iconutil requires for a complete .iconset.
ICONSET_SIZES = [
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
]

# Apple Color Emoji is a fixed-size "strike" bitmap font — render once at its
# largest natural strike, then downscale for every smaller icon size, rather
# than asking the font for each size individually (which can upscale a small
# strike and look blocky at large sizes instead of just softening slightly).
MASTER_FONT_SIZE = 160
MASTER_CANVAS_SIZE = 1024
PADDING_FRACTION = 0.08  # margin around the glyph, as a fraction of canvas size


def render_master(emoji: str) -> Image.Image:
    font = ImageFont.truetype(FONT_PATH, size=MASTER_FONT_SIZE)

    # textbbox() doesn't return a tight ink box for color/embedded glyphs —
    # it reports the character cell, not where pixels actually land (Apple
    # Color Emoji glyphs render offset from the nominal origin). Draw onto a
    # generously padded probe canvas and use Image.getbbox() to find the
    # real non-transparent extent instead.
    probe = Image.new("RGBA", (MASTER_FONT_SIZE * 3, MASTER_FONT_SIZE * 3), (0, 0, 0, 0))
    probe_draw = ImageDraw.Draw(probe)
    probe_draw.text((MASTER_FONT_SIZE, MASTER_FONT_SIZE), emoji, font=font, embedded_color=True)
    bbox = probe.getbbox()
    glyph_w, glyph_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    glyph = probe.crop(bbox)
    target = MASTER_CANVAS_SIZE * (1 - 2 * PADDING_FRACTION)
    scale = target / max(glyph_w, glyph_h)
    glyph = glyph.resize(
        (max(1, round(glyph_w * scale)), max(1, round(glyph_h * scale))), Image.LANCZOS
    )

    canvas = Image.new("RGBA", (MASTER_CANVAS_SIZE, MASTER_CANVAS_SIZE), (0, 0, 0, 0))
    x = (MASTER_CANVAS_SIZE - glyph.width) // 2
    y = (MASTER_CANVAS_SIZE - glyph.height) // 2
    canvas.paste(glyph, (x, y), glyph)
    return canvas


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    emoji, out_dir = sys.argv[1], Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    master = render_master(emoji)
    for filename, size in ICONSET_SIZES:
        resized = master.resize((size, size), Image.LANCZOS)
        resized.save(out_dir / filename)

    print(f"Wrote {len(ICONSET_SIZES)} sizes to {out_dir}")


if __name__ == "__main__":
    main()
