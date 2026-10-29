from PIL import Image, ImageDraw

from . import graphics as g
from . import media
from .project import H, W
from .render import build_static_assets

GRID_CROP = (0, 240, W, H - 240)
FEED_CROP = (0, 285, W, H - 285)


def title_card(style, lines, subtitle, size=104):
    fnt = style.font("black", size)
    line_h = int(size * 1.08)
    texts = [g.text_img(line, fnt, style.ink) for line in lines]
    chip = g.pill(subtitle, style.font("black", 34), style.white, style.accent, pad=(26, 12)) if subtitle else None
    pad = 50
    w = max([t.width for t in texts] + ([chip.width] if chip else [])) + 2 * pad
    h = pad + len(texts) * line_h + (28 + chip.height if chip else 0) + pad
    card = g.solid(w, h, style.white, r=40, alpha=238)
    y = pad - int(size * 0.12)
    for t in texts:
        card.alpha_composite(t, ((w - t.width) // 2, y))
        y += line_h
    if chip:
        card.alpha_composite(chip, ((w - chip.width) // 2, h - pad - chip.height))
    return g.shadowed(card)


def with_title(style, base, cfg, center_y=1330):
    canvas = base.convert("RGBA").resize((W, H), Image.LANCZOS)
    sprite = title_card(style, cfg["title"], cfg["subtitle"])
    w, h = g.sprite_size(sprite)
    g.put_shadowed(canvas, sprite, (W - w) // 2, center_y - h // 2)
    return canvas


def preview_sheet(style, covers, path, scale=0.5, gap=30, label_h=60):
    col_w = int(W * scale)
    sheet = Image.new("RGB", (gap + 3 * (col_w + gap), gap + len(covers) * (label_h + int(H * scale) + gap)), "white")
    d = ImageDraw.Draw(sheet)
    y = gap
    for name, img in covers:
        views = [("Reels 9:16", img), ("Profile grid 3:4", img.crop(GRID_CROP)), ("Feed 4:5", img.crop(FEED_CROP))]
        for k, (label, view) in enumerate(views):
            x = gap + k * (col_w + gap)
            d.text((x, y + 10), f"{name} - {label}", font=style.font("black", 30), fill=style.ink)
            sheet.paste(view.convert("RGB").resize((col_w, int(view.height * scale)), Image.LANCZOS), (x, y + label_h))
        y += label_h + int(H * scale) + gap
    sheet.save(path)


def make_covers(project, log=print):
    cfg = project.conf("cover")
    style = project.style
    out_dir = project.out_dir("cover")
    build_static_assets(project)
    background = project.bg_png
    if project.ambient_src.exists():
        media.build_ambient(project.ambient_src, project.bg_png, project.ambient_loop,
                            project.conf("ambient")["opacity"], project.fps, W, H)
        background = project.ambient_loop
    tmp = project.build / "cover-frame.png"
    media.composite_frame(project.avatar_video, background, cfg["avatar_at"], tmp, project.fps,
                          project.conf("avatar")["key_color"])
    covers = [("A", with_title(style, Image.open(tmp), cfg))]
    if project.hook_src.exists():
        media.frame_at(project.hook_src, cfg["hook_at"], tmp)
        covers.append(("B", with_title(style, Image.open(tmp), cfg)))
    tmp.unlink(missing_ok=True)
    for name, img in covers:
        path = out_dir / f"cover-{name}.jpg"
        img.convert("RGB").save(path, quality=95)
        log(f"Saved {path}")
    preview_sheet(style, covers, out_dir / "cover-preview.jpg")
    log(f"Saved {out_dir / 'cover-preview.jpg'} (how each cover looks in the Reels player, profile grid and feed)")
