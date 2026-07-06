"""Generate the SelfScribe app icon (a microphone) as a multi-size .ico.

Drawn at runtime with Pillow (already a dependency) so no binary lives in the
repo. Written to %USERPROFILE%\\.selfscribe\\selfscribe.ico when the desktop
shortcut is installed.
"""

from pathlib import Path

from PIL import Image, ImageDraw

from selfscribe.config import DEFAULT_CONFIG_DIR

BG = (37, 99, 235, 255)  # indigo-blue rounded tile
FG = (255, 255, 255, 255)  # white mic
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def render_icon(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size

    # rounded background tile
    pad = round(s * 0.06)
    d.rounded_rectangle([pad, pad, s - pad, s - pad], radius=round(s * 0.22), fill=BG)

    # mic capsule (rounded vertical pill)
    cap_w = round(s * 0.24)
    cx = s / 2
    cap_left = round(cx - cap_w / 2)
    cap_right = round(cx + cap_w / 2)
    cap_top = round(s * 0.20)
    cap_bottom = round(s * 0.52)
    d.rounded_rectangle([cap_left, cap_top, cap_right, cap_bottom], radius=cap_w // 2, fill=FG)

    stroke = max(2, round(s * 0.045))

    # cradle: a U-arc hugging the lower half of the capsule
    cradle_w = round(cap_w * 1.9)
    cradle = [
        round(cx - cradle_w / 2),
        round(cap_top + (cap_bottom - cap_top) * 0.35),
        round(cx + cradle_w / 2),
        round(cap_bottom + (cap_bottom - cap_top) * 0.30),
    ]
    d.arc(cradle, start=20, end=160, fill=FG, width=stroke)

    # stem down to the base
    stem_top = cradle[3] - stroke // 2
    stem_bottom = round(s * 0.80)
    d.line([(cx, stem_top), (cx, stem_bottom)], fill=FG, width=stroke)

    # base foot
    foot_w = round(s * 0.20)
    d.line(
        [(cx - foot_w / 2, stem_bottom), (cx + foot_w / 2, stem_bottom)],
        fill=FG,
        width=stroke,
    )
    return img


def icon_path() -> Path:
    return DEFAULT_CONFIG_DIR / "selfscribe.ico"


def write_ico(path: Path | None = None) -> Path:
    path = path or icon_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    base = render_icon(256)
    base.save(path, format="ICO", sizes=[(n, n) for n in ICO_SIZES])
    return path
