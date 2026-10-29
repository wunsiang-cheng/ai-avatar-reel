from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIRS = [
    Path(__file__).resolve().parent.parent / "assets" / "fonts",
    Path.home() / ".local" / "share" / "fonts",
    Path.home() / ".fonts",
    Path.home() / "Library" / "Fonts",
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts"),
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path("C:/Windows/Fonts"),
]


def hex_color(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


@dataclass
class Style:
    bg_top: tuple = (247, 245, 241)
    bg_bottom: tuple = (232, 235, 241)
    ink: tuple = (28, 31, 38)
    muted: tuple = (107, 114, 128)
    accent: tuple = (59, 91, 219)
    accent_soft: tuple = (231, 236, 255)
    white: tuple = (255, 255, 255)
    code_bg: tuple = (245, 246, 248)
    line: tuple = (226, 229, 235)
    bar_idle: tuple = (210, 214, 222)
    caption_y: int = 1460
    fonts: dict = field(default_factory=lambda: {
        "black": "Lato-Black.ttf",
        "heavy": "Lato-Heavy.ttf",
        "bold": "Lato-Bold.ttf",
        "medium": "Lato-Medium.ttf",
        "mono": "DejaVuSansMono.ttf",
        "mono_bold": "DejaVuSansMono-Bold.ttf",
    })

    @classmethod
    def from_config(cls, cfg):
        style = cls()
        for key, value in cfg.items():
            if key == "fonts":
                style.fonts = {**style.fonts, **value}
            elif isinstance(value, str) and value.startswith("#"):
                setattr(style, key, hex_color(value))
            else:
                setattr(style, key, value)
        return style

    def font(self, role, size):
        return font(self.fonts[role], size)


@lru_cache(maxsize=None)
def find_font(filename):
    path = Path(filename)
    if path.is_absolute():
        return path if path.exists() else None
    for directory in FONT_DIRS:
        if directory.is_dir():
            hit = next(directory.rglob(filename), None)
            if hit:
                return hit
    return None


@lru_cache(maxsize=None)
def font(filename, size):
    path = find_font(filename)
    if path is None:
        raise SystemExit(f"Font not found: {filename}. Install it (Lato and DejaVu Sans Mono are free) "
                         f"or put the .ttf file in assets/fonts/, or change [style.fonts] in project.toml.")
    return ImageFont.truetype(str(path), size)


def rounded_mask(w, h, r, ss=3):
    big = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), r * ss, fill=255)
    return big.resize((w, h), Image.LANCZOS)


def circle_mask(d, ss=3):
    big = Image.new("L", (d * ss, d * ss), 0)
    ImageDraw.Draw(big).ellipse((0, 0, d * ss - 1, d * ss - 1), fill=255)
    return big.resize((d, d), Image.LANCZOS)


def solid(w, h, color, r=0, alpha=255):
    img = Image.new("RGBA", (w, h), color + (alpha,))
    if r:
        mask = rounded_mask(w, h, r)
        if alpha < 255:
            mask = mask.point(lambda v: v * alpha // 255)
        img.putalpha(mask)
    return img


def shadowed(img, blur=22, offset=(0, 12), opacity=38, margin=48):
    out = Image.new("RGBA", (img.width + 2 * margin, img.height + 2 * margin), (0, 0, 0, 0))
    shadow = Image.new("RGBA", img.size, (20, 24, 40, 0))
    shadow.putalpha(img.getchannel("A").point(lambda v: v * opacity // 255))
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    layer.alpha_composite(shadow, (margin + offset[0], margin + offset[1]))
    out.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))
    out.alpha_composite(img, (margin, margin))
    return out, margin


def text_img(s, fnt, color):
    asc, desc = fnt.getmetrics()
    img = Image.new("RGBA", (int(np.ceil(fnt.getlength(s))) + 2, asc + desc), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((0, asc), s, font=fnt, fill=color, anchor="ls")
    return img


def pill(s, fnt, fg, bg, pad=(26, 12), alpha=255):
    label = text_img(s, fnt, fg)
    w, h = label.width + 2 * pad[0], label.height + 2 * pad[1]
    img = solid(w, h, bg, r=h // 2, alpha=alpha)
    img.alpha_composite(label, (pad[0], pad[1]))
    return img


def wrap(s, fnt, max_w):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if fnt.getlength(trial) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def rounded_image(img, w, h, r):
    img = img.convert("RGBA").resize((w, h), Image.LANCZOS)
    img.putalpha(rounded_mask(w, h, r))
    return img


def cover_crop(img, w, h):
    scale = max(w / img.width, h / img.height)
    resized = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def arrow_down(color, length=50, width=6, head=16):
    ss = 3
    w = head * 2 + 4
    big = Image.new("RGBA", (w * ss, length * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    cx = w * ss // 2
    d.line((cx, 0, cx, (length - head) * ss), fill=color, width=width * ss)
    d.polygon([(cx - head * ss, (length - head) * ss), (cx + head * ss, (length - head) * ss),
               (cx, length * ss - 1)], fill=color)
    return big.resize((w, length), Image.LANCZOS)


def play_icon(size, color):
    ss = 3
    big = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    ImageDraw.Draw(big).polygon([(0, 0), (size * ss - 1, size * ss // 2), (0, size * ss - 1)], fill=color)
    return big.resize((size, size), Image.LANCZOS)


def ring(d, width, color):
    ss = 3
    big = Image.new("RGBA", (d * ss, d * ss), (0, 0, 0, 0))
    ImageDraw.Draw(big).ellipse((0, 0, d * ss - 1, d * ss - 1), outline=color, width=width * ss)
    return big.resize((d, d), Image.LANCZOS)


def hstack(images, gap=0):
    h = max(i.height for i in images)
    out = Image.new("RGBA", (sum(i.width for i in images) + gap * (len(images) - 1), h), (0, 0, 0, 0))
    x = 0
    for img in images:
        out.alpha_composite(img, (x, (h - img.height) // 2))
        x += img.width + gap
    return out


def fade(t, start, dur=0.25):
    if start is None:
        return 1.0
    return max(0.0, min(1.0, (t - start) / dur))


def put(canvas, img, x, y, opacity=1.0):
    if opacity <= 0:
        return
    if opacity < 1:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * opacity)))
    canvas.alpha_composite(img, (int(x), int(y)))


def put_shadowed(canvas, sprite, x, y, opacity=1.0):
    img, margin = sprite
    put(canvas, img, x - margin, y - margin, opacity)


def sprite_size(sprite):
    img, margin = sprite
    return img.width - 2 * margin, img.height - 2 * margin


def gradient(w, h, top, bottom):
    ramp = np.linspace(0, 1, h)[:, None]
    bg = np.zeros((h, w, 3), dtype=np.uint8)
    for c in range(3):
        bg[:, :, c] = (top[c] * (1 - ramp) + bottom[c] * ramp).astype(np.uint8)
    return bg
