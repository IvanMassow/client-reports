#!/usr/bin/env python3
"""Generate the Open Graph sharing image for Sovereign Signal."""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).parent.resolve()
OUTPUT = SCRIPT_DIR / "og-image.png"
FLAG_PATH = SCRIPT_DIR / "union-flag.png"
W, H = 1200, 630

# Colours matching dashboard.css
SLATE_DEEP = (26, 30, 39)


def load_font(name, size):
    """Try to load a font, falling back to default."""
    search = [
        f"/System/Library/Fonts/{name}.ttc",
        f"/System/Library/Fonts/Supplemental/{name}.ttf",
        f"/Library/Fonts/{name}.ttf",
        f"/Library/Fonts/{name}.otf",
    ]
    for path in search:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    # Try by name directly
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return ImageFont.load_default()


def main():
    # Create base image
    img = Image.new("RGB", (W, H), SLATE_DEEP)
    draw = ImageDraw.Draw(img)

    # Load and composite the Union Jack
    if FLAG_PATH.exists():
        flag = Image.open(FLAG_PATH).convert("RGB")
        # Resize to cover, crop to fit
        flag_ratio = max(W / flag.width, H / flag.height)
        flag = flag.resize(
            (int(flag.width * flag_ratio), int(flag.height * flag_ratio)),
            Image.LANCZOS,
        )
        # Center crop
        left = (flag.width - W) // 2
        top = (flag.height - H) // 2
        flag = flag.crop((left, top, left + W, top + H))

        # Desaturate slightly
        from PIL import ImageEnhance
        flag = ImageEnhance.Color(flag).enhance(0.55)
        flag = ImageEnhance.Contrast(flag).enhance(1.1)

        # Blend with base at 45% opacity
        img = Image.blend(img, flag, 0.45)
        draw = ImageDraw.Draw(img)

    # Apply gradient overlay (dark left, transparent right)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for x in range(W):
        # Gradient: nearly opaque at left, fading out to right
        t = x / W
        if t < 0.30:
            alpha = int(245)
        elif t < 0.55:
            frac = (t - 0.30) / 0.25
            alpha = int(245 - frac * 140)
        else:
            frac = (t - 0.55) / 0.45
            alpha = int(105 - frac * 75)
        odraw.line([(x, 0), (x, H)], fill=(*SLATE_DEEP, alpha))

    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)

    # Load fonts
    font_title = load_font("Georgia", 72)
    font_eyebrow = load_font("Helvetica", 14)
    font_subtitle = load_font("Georgia", 19)
    font_brand = load_font("Helvetica", 14)
    font_brand_label = load_font("Helvetica", 11)

    x_left = 72

    # Eyebrow: "UNITED KINGDOM"
    draw.text(
        (x_left, 215),
        "UNITED KINGDOM",
        fill=(255, 255, 255, 90),
        font=font_eyebrow,
    )

    # Title: "Sovereign Signal"
    draw.text((x_left, 255), "Sovereign", fill=(255, 255, 255, 255), font=font_title)
    draw.text((x_left, 330), "Signal", fill=(255, 255, 255, 255), font=font_title)

    # Subtitle
    draw.text(
        (x_left, 416),
        "National standing intelligence report",
        fill=(255, 255, 255, 97),
        font=font_subtitle,
    )

    # Brand
    draw.text((x_left, 568), "NOAH", fill=(255, 255, 255, 72), font=font_brand)
    # Divider
    draw.line([(x_left + 54, 558), (x_left + 54, 578)], fill=(255, 255, 255, 26), width=1)
    draw.text(
        (x_left + 66, 570),
        "WIRE SERVICES",
        fill=(255, 255, 255, 46),
        font=font_brand_label,
    )

    # Bottom line
    draw.line([(0, H - 1), (W, H - 1)], fill=(255, 255, 255, 20), width=1)

    # Save
    img = img.convert("RGB")
    img.save(OUTPUT, "PNG", quality=95)
    print(f"OG image saved: {OUTPUT}")
    print(f"Size: {OUTPUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
