import wave

import numpy as np
from PIL import Image, ImageDraw

from . import graphics as g
from .project import H, W
from .timeline import Timeline, caption_chunks

CARD_X, CARD_Y, CARD_W = 60, 300, 960
CARD_PAD, CONTENT_TOP, BLOCK_GAP = 40, 120, 20
INNER_W = CARD_W - 2 * CARD_PAD
CIRCLE_D, CIRCLE_POS = 340, (80, 1065)
OUTPUT_SIZE, OUTPUT_POS = (420, 630), (580, 440)
LAYOUTS = ("full", "split", "pip", "compare")


def pill_colors(style, kind):
    return {"accent": (style.white, style.accent), "dark": (style.white, style.ink),
            "light": (style.ink, style.white), "soft": (style.accent, style.accent_soft)}[kind]


class Context:
    def __init__(self, project, style, timeline, scene_start, scene_end):
        self.project, self.style, self.timeline = project, style, timeline
        self.start, self.end = scene_start, scene_end

    def at(self, value, lead=0.1):
        if value is None:
            return None
        return self.timeline.resolve(value, after=self.start, lead=lead)


class Block:
    height = 0

    def __init__(self, cfg, ctx):
        self.cfg, self.ctx, self.style = cfg, ctx, ctx.style
        self.at = ctx.at(cfg.get("at"))
        self.replace = cfg.get("replace", False)

    def draw(self, canvas, x, y, t, opacity):
        raise NotImplementedError


class CodeBlock(Block):
    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        s = self.style
        self.height = cfg.get("height", 470)
        text = cfg.get("text") or ctx.project.path(cfg["text_file"]).read_text()
        self.text = " ".join(text.split())[:cfg.get("max_chars", 280)]
        self.font = s.font("mono", cfg.get("size", 29))
        self.lines = g.wrap(self.text, self.font, INNER_W - 60)[:(self.height - 100) // 42]
        win = g.solid(INNER_W, self.height, s.code_bg, r=20)
        for k, color in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
            win.alpha_composite(g.solid(16, 16, color, r=8), (26 + k * 26, 22))
        win.alpha_composite(g.text_img(cfg.get("label", ""), s.font("mono", 24), s.muted), (112, 15))
        ImageDraw.Draw(win).line((0, 60, INNER_W, 60), fill=s.line, width=2)
        self.window = win
        self.type_start = ctx.start + cfg.get("delay", 0.5) if self.at is None else self.at
        self.cps = len(self.text) / cfg.get("type_seconds", 3.2)

    def draw(self, canvas, x, y, t, opacity):
        win = self.window.copy()
        d = ImageDraw.Draw(win)
        asc = self.font.getmetrics()[0]
        remaining = int(max(0.0, t - self.type_start) * self.cps)
        tx, ty = 28, 84
        cursor = (tx, ty)
        for line in self.lines:
            if remaining <= 0:
                break
            part = line[:remaining]
            d.text((tx, ty + asc), part, font=self.font, fill=self.style.ink, anchor="ls")
            cursor = (tx + self.font.getlength(part) + 2, ty)
            remaining -= len(line) + 1
            ty += 42
        if int(t * 3) % 2 == 0:
            d.rectangle((cursor[0], cursor[1] + 6, cursor[0] + 15, cursor[1] + asc + 4), fill=self.style.accent)
        g.put(canvas, win, x, y, opacity)


class MediaBlock(Block):
    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        s = self.style
        self.height = cfg.get("height", 470)
        image = Image.open(ctx.project.asset(cfg.get("image", "@portrait")))
        thumb_w = round(self.height * image.width / image.height)
        view = Image.new("RGBA", (INNER_W, self.height), (0, 0, 0, 0))
        view.alpha_composite(g.rounded_image(image, thumb_w, self.height, 20), (0, 0))
        col = thumb_w + 46
        y = 6
        if cfg.get("tag"):
            view.alpha_composite(g.pill(cfg["tag"], s.font("black", 24), s.accent, s.accent_soft, pad=(16, 6)), (col, y))
        if cfg.get("title"):
            view.alpha_composite(g.text_img(cfg["title"], s.font("mono_bold", 30), s.ink), (col, y + 64))
        if cfg.get("subtitle"):
            view.alpha_composite(g.text_img(cfg["subtitle"], s.font("bold", 36), s.ink), (col, y + 112))
        for k, line in enumerate(cfg.get("lines", [])):
            view.alpha_composite(g.text_img(line, s.font("mono", 26), s.muted), (col, y + 186 + k * 44))
        self.view = view

    def draw(self, canvas, x, y, t, opacity):
        g.put(canvas, self.view, x, y, opacity)


class QuoteBlock(Block):
    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        s = self.style
        fnt = s.font("medium", cfg.get("size", 36))
        lines = g.wrap(cfg["text"], fnt, INNER_W)
        label_h = 40 if cfg.get("label") else 0
        line_h = int(cfg.get("size", 36) * 1.33)
        self.height = label_h + len(lines) * line_h
        img = Image.new("RGBA", (INNER_W, self.height + 20), (0, 0, 0, 0))
        if cfg.get("label"):
            img.alpha_composite(g.text_img(cfg["label"], s.font("mono", 25), s.muted), (0, 6))
        for k, line in enumerate(lines):
            img.alpha_composite(g.text_img(line, fnt, s.ink), (0, label_h + k * line_h))
        self.img = img

    def draw(self, canvas, x, y, t, opacity):
        g.put(canvas, self.img, x, y, opacity)


class WaveformBlock(Block):
    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.height = cfg.get("height", 200)
        bars = cfg.get("bars", 64)
        with wave.open(str(ctx.project.asset(cfg.get("audio", "@narration")))) as wf:
            samples = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)
        rms = np.array([np.sqrt(np.mean(c ** 2)) for c in np.array_split(samples, bars)])
        self.levels = (rms / rms.max()) ** 0.7
        self.progress = (ctx.start + 0.3, ctx.end - 0.2)

    def draw(self, canvas, x, y, t, opacity):
        img = Image.new("RGBA", (INNER_W, self.height), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        start, end = self.progress
        progress = max(0.0, min(1.0, (t - start) / max(end - start, 0.1)))
        n, bar_w = len(self.levels), 8
        gap = (INNER_W - n * bar_w) / (n - 1)
        for i, level in enumerate(self.levels):
            bh = max(8, level * self.height)
            bx, by = i * (bar_w + gap), (self.height - bh) / 2
            color = self.style.accent if i < progress * n else self.style.bar_idle
            d.rounded_rectangle((bx, by, bx + bar_w, by + bh), radius=bar_w // 2, fill=color)
        g.put(canvas, img, x, y, opacity)


class FlowBlock(Block):
    ROW, ROW_H = 15, 300

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        s = self.style
        self.items = []
        plus = g.text_img("+", s.font("black", 72), s.muted)
        for k, item in enumerate(cfg.get("inputs", [])):
            if "image" in item:
                image = Image.open(ctx.project.asset(item["image"]))
                img = g.rounded_image(image, round(self.ROW_H * image.width / image.height), self.ROW_H, 16)
            else:
                img = self.tile(item.get("tile", ""), item.get("sub", ""))
            at = ctx.at(item.get("at"))
            if k:
                self.items.append((plus, at))
            self.items.append((img, at))
        self.arrow = g.arrow_down(s.accent, 50)
        self.model = g.pill(cfg.get("model", ""), s.font("mono_bold", 34), s.white, s.ink, pad=(30, 14))
        out_text = g.text_img(cfg.get("output", ""), s.font("bold", 32), s.ink)
        self.output = g.hstack([g.play_icon(26, s.accent), out_text], gap=14)
        self.model_at = ctx.at(cfg.get("model_at"))
        self.arrow_at = ctx.at(cfg.get("arrow_at", cfg.get("model_at")))
        self.output_at = ctx.at(cfg.get("output_at"))
        self.height = 590

    def tile(self, label, sub):
        s = self.style
        tile = g.solid(300, 300, s.accent_soft, r=24)
        d = ImageDraw.Draw(tile)
        heights = [40, 90, 140, 70, 160, 110, 60, 120, 50]
        bx = (300 - (len(heights) * 14 + (len(heights) - 1) * 10)) // 2
        for k, bh in enumerate(heights):
            d.rounded_rectangle((bx + k * 24, 120 - bh / 2, bx + k * 24 + 14, 120 + bh / 2), radius=7, fill=s.accent)
        text = g.text_img(label, s.font("bold", 30), s.ink)
        tile.alpha_composite(text, ((300 - text.width) // 2, 212))
        if sub:
            sub_img = g.text_img(sub, s.font("mono", 25), s.muted)
            tile.alpha_composite(sub_img, ((300 - sub_img.width) // 2, 254))
        return tile

    def draw(self, canvas, x, y, t, opacity):
        gap = 40
        row_w = sum(img.width for img, _ in self.items) + gap * (len(self.items) - 1)
        cx = x + INNER_W // 2
        ix = cx - row_w // 2
        for img, at in self.items:
            g.put(canvas, img, ix, y + self.ROW + (self.ROW_H - img.height) // 2, opacity * g.fade(t, at))
            ix += img.width + gap
        g.put(canvas, self.model, cx - self.model.width // 2, y + 395, opacity * g.fade(t, self.model_at))
        g.put(canvas, self.arrow, cx - self.arrow.width // 2, y + 335, opacity * g.fade(t, self.arrow_at))
        b = opacity * g.fade(t, self.output_at)
        g.put(canvas, self.arrow, cx - self.arrow.width // 2, y + 485, b)
        g.put(canvas, self.output, cx - self.output.width // 2, y + 548, b)


class MonoBlock(Block):
    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.imgs = [g.text_img(line, self.style.font("mono", cfg.get("size", 25)), self.style.muted)
                     for line in cfg.get("lines", [])]
        self.height = 38 * len(self.imgs)

    def draw(self, canvas, x, y, t, opacity):
        for k, img in enumerate(self.imgs):
            g.put(canvas, img, x, y + k * 38, opacity)


BLOCKS = {"code": CodeBlock, "media": MediaBlock, "quote": QuoteBlock, "waveform": WaveformBlock,
          "flow": FlowBlock, "mono": MonoBlock}


def header(style, step, title):
    chip = g.pill(step, style.font("black", 28), style.white, style.accent, pad=(18, 8)) if step else None
    heading = g.text_img(title, style.font("black", 48), style.ink)
    return g.hstack([chip, heading], gap=20) if chip else heading


class Card:
    def __init__(self, cfg, ctx):
        self.ctx = ctx
        self.blocks = []
        for block_cfg in cfg.get("blocks", []):
            kind = block_cfg.get("type")
            if kind not in BLOCKS:
                raise SystemExit(f"Unknown block type '{kind}'. Use one of: {', '.join(BLOCKS)}")
            self.blocks.append(BLOCKS[kind](block_cfg, ctx))
        self.offsets = []
        y = CONTENT_TOP
        prev_y = y
        for block in self.blocks:
            if block.replace and self.offsets:
                self.offsets.append(prev_y)
                continue
            prev_y = y
            self.offsets.append(y)
            y += block.height + BLOCK_GAP
        height = cfg.get("height", y - BLOCK_GAP + CARD_PAD)
        card = g.solid(CARD_W, height, ctx.style.white, r=36)
        card.alpha_composite(header(ctx.style, cfg.get("step"), cfg.get("title", "")), (CARD_PAD, CARD_PAD))
        self.sprite = g.shadowed(card)

    def draw(self, canvas, t):
        enter = g.fade(t, self.ctx.start, 0.2)
        g.put_shadowed(canvas, self.sprite, CARD_X, CARD_Y, enter)
        for k, (block, y) in enumerate(zip(self.blocks, self.offsets)):
            opacity = enter * g.fade(t, block.at, 0.35 if block.replace else 0.25)
            nxt = self.blocks[k + 1] if k + 1 < len(self.blocks) else None
            if nxt is not None and nxt.replace:
                opacity *= 1 - g.fade(t, nxt.at, 0.35)
            block.draw(canvas, CARD_X + CARD_PAD, CARD_Y + y, t, opacity)


class Overlay:
    def __init__(self, cfg, ctx, earliest):
        s = ctx.style
        self.y = cfg.get("y", 1150)
        size, gap = cfg.get("size", 40), cfg.get("gap", 18)
        if cfg.get("type") == "badge":
            items = [{"text": cfg["text"], "style": cfg.get("style", "accent"), "at": cfg.get("at")}]
            size = cfg.get("size", 42)
        elif cfg.get("type") == "pills":
            items = cfg["items"]
        else:
            raise SystemExit(f"Unknown overlay type '{cfg.get('type')}'. Use 'badge' or 'pills'.")
        self.items = []
        for item in items:
            fg, bg = pill_colors(s, item.get("style", "accent"))
            sprite = g.shadowed(g.pill(item["text"], s.font("black", size), fg, bg, pad=(int(size * 0.8), 14)))
            at = ctx.at(item.get("at"))
            at = ctx.start if at is None else at
            self.items.append((sprite, max(at, earliest)))
        self.gap = gap
        self.fade = cfg.get("fade", 0.3 if cfg.get("type") == "badge" else 0.25)

    def draw(self, canvas, t):
        widths = [g.sprite_size(sprite)[0] for sprite, _ in self.items]
        x = (W - (sum(widths) + self.gap * (len(widths) - 1))) / 2
        for (sprite, at), w in zip(self.items, widths):
            g.put_shadowed(canvas, sprite, x, self.y, g.fade(t, at, self.fade))
            x += w + self.gap


class Scene:
    def __init__(self, cfg, ctx, framing, earliest):
        self.cfg, self.ctx, self.style = cfg, ctx, ctx.style
        self.start, self.end = ctx.start, ctx.end
        self.layout = cfg.get("layout", "full")
        if self.layout not in LAYOUTS:
            raise SystemExit(f"Unknown layout '{self.layout}'. Use one of: {', '.join(LAYOUTS)}")
        self.card = Card(cfg["card"], ctx) if "card" in cfg else None
        self.overlays = [Overlay(o, ctx, earliest) for o in cfg.get("overlays", [])]
        if self.layout == "split":
            self.feather = split_feather(ctx.style, framing)
        if self.layout == "pip":
            self.build_pip(cfg.get("pip", {}))
        if self.layout == "compare":
            self.build_compare(cfg.get("compare", {}), framing)

    def build_pip(self, cfg):
        s = self.style
        ring_img = g.ring(CIRCLE_D + 16, 9, s.white)
        self.ring = g.shadowed(ring_img, blur=16, offset=(0, 8), opacity=60, margin=36)
        tag = g.pill(cfg.get("tag", "● LIVE"), s.font("black", 28), s.white, s.accent, pad=(18, 8))
        note = g.text_img(cfg.get("note", ""), s.font("mono", 26), s.muted)
        box = Image.new("RGBA", (max(tag.width, note.width), tag.height + 12 + note.height), (0, 0, 0, 0))
        box.alpha_composite(tag, (0, 0))
        box.alpha_composite(note, (0, tag.height + 12))
        self.live = box

    def build_compare(self, cfg, framing):
        s = self.style
        self.compare_header = header(s, cfg.get("step"), cfg.get("title", ""))
        cw, ch, ix, iy = 460, 720, 20, 70
        iw, ih = OUTPUT_SIZE
        portrait = Image.open(self.ctx.project.asset(cfg.get("image", "@portrait"))).convert("RGBA")
        scale = W / portrait.width
        ow, oh, ox, oy = framing["compare_crop"]
        still = portrait.crop(tuple(int(v / scale) for v in (ox, oy, ox + ow, oy + oh)))
        left = g.solid(cw, ch, s.white, r=32)
        self.label_row(left, cfg.get("input_label", "INPUT"), s.ink, cfg.get("input_text", ""))
        left.alpha_composite(g.rounded_image(still, iw, ih, 20), (ix, iy))
        right = g.solid(cw, ch, s.white, r=32)
        self.label_row(right, cfg.get("output_label", "OUTPUT"), s.accent, cfg.get("output_text", ""))
        hole = Image.new("L", (cw, ch), 255)
        hole.paste(Image.eval(g.rounded_mask(iw, ih, 20), lambda v: 255 - v), (ix, iy))
        right.putalpha(Image.fromarray(np.minimum(np.array(right.getchannel("A")), np.array(hole))))
        self.compare_cards = (g.shadowed(left), g.shadowed(right))

    def label_row(self, card, chip_text, chip_color, text):
        s = self.style
        chip = g.pill(chip_text, s.font("black", 24), s.white, chip_color, pad=(16, 6))
        card.alpha_composite(chip, (20, 22))
        label = g.text_img(text, s.font("bold", 30), s.ink)
        card.alpha_composite(label, (20 + chip.width + 14, 22 + (chip.height - label.height) // 2))

    def draw(self, canvas, t):
        enter = g.fade(t, self.start, 0.2)
        if self.layout == "split":
            g.put(canvas, *self.feather)
        if self.card:
            self.card.draw(canvas, t)
        if self.layout == "pip":
            g.put_shadowed(canvas, self.ring, CIRCLE_POS[0] - 8, CIRCLE_POS[1] - 8, enter)
            g.put(canvas, self.live, CIRCLE_POS[0] + CIRCLE_D + 40,
                  CIRCLE_POS[1] + CIRCLE_D // 2 - self.live.height // 2, enter)
        if self.layout == "compare":
            g.put(canvas, self.compare_header, CARD_X, CARD_Y - 10, enter)
            g.put_shadowed(canvas, self.compare_cards[0], 60, 370, enter)
            g.put_shadowed(canvas, self.compare_cards[1], 560, 370, enter)
        for overlay in self.overlays:
            overlay.draw(canvas, t)


def split_box(framing):
    w = round(W * framing["split_scale"] / 2) * 2
    h = round(H * framing["split_scale"] / 2) * 2
    return w, h, (W - w) // 2, framing["split_top"]


def split_feather(style, framing, fade_in=100, bleed=6):
    w, _, x, _ = split_box(framing)
    top, ramp = framing["feather_top"], framing["feather_ramp"]
    x0, w = x - bleed, w + 2 * bleed
    rgb = g.gradient(W, H, style.bg_top, style.bg_bottom)[top:, x0:x0 + w]
    xs = np.arange(w)
    edge = np.maximum(np.minimum(xs, w - 1 - xs) - bleed, 0)
    horizontal = np.clip(1 - edge / ramp, 0, 1)[None, :]
    vertical = np.clip(np.arange(H - top) / fade_in, 0, 1)[:, None]
    alpha = (255 * horizontal * vertical).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA"), x0, top


class Composer:
    def __init__(self, project, use_hook=False):
        self.project = project
        self.style = style = project.style
        self.fps = project.fps
        captions = project.conf("captions")
        self.timeline = Timeline(project.script_text, project.words(), captions.get("aliases"))
        framing = project.conf("framing")
        hook = project.conf("hook")
        self.hook_end = hook["end"] if use_hook else 0.0
        earliest_first = hook["end"] + 0.2 if use_hook else 0.0

        if not project.scenes:
            raise SystemExit("project.toml has no [[scenes]].")
        starts = []
        for k, cfg in enumerate(project.scenes):
            start = cfg.get("start", 0)
            if k == 0:
                t = 0.0
            elif isinstance(start, (int, float)):
                t = float(start)
            else:
                t = self.timeline.find(start, after=starts[-1])[0] - cfg.get("lead", 0.05)
            starts.append(round(t * self.fps) / self.fps)
        ends = starts[1:] + [1e6]
        self.scenes = []
        for k, cfg in enumerate(project.scenes):
            ctx = Context(project, style, self.timeline, starts[k], ends[k])
            self.scenes.append(Scene(cfg, ctx, framing, earliest_first if k == 0 else 0.0))

        self.captions = []
        for start, end, words in caption_chunks(self.timeline, captions["keep_together"],
                                                captions["max_chars"], captions["max_words"]):
            self.captions.append((start, end, self.caption_img(words, captions["highlight"])))

    def caption_img(self, words, highlight):
        s = self.style
        hl = {self.timeline.norm(h) for h in highlight}
        fnt = s.font("heavy", 56)
        asc, desc = fnt.getmetrics()
        parts = [w.rstrip(".,:") for w in words]
        widths = [fnt.getlength(p) for p in parts]
        space = fnt.getlength(" ")
        pad_x, pad_y = 30, 12
        img = g.solid(int(sum(widths) + space * (len(parts) - 1)) + 2 * pad_x, asc + desc + 2 * pad_y,
                      s.white, r=22, alpha=242)
        d = ImageDraw.Draw(img)
        x = pad_x
        for part, pw in zip(parts, widths):
            color = s.accent if self.timeline.norm(part) in hl else s.ink
            d.text((x, pad_y + asc), part, font=fnt, fill=color, anchor="ls")
            x += pw + space
        return g.shadowed(img, blur=14, offset=(0, 6), opacity=45, margin=30)

    def windows(self, layout):
        return [(s.start, s.end) for s in self.scenes if s.layout == layout]

    def frame(self, t, captions=True):
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for scene in self.scenes:
            if scene.start <= t < scene.end:
                scene.draw(canvas, t)
                break
        if captions:
            for start, end, sprite in self.captions:
                if start <= t < end:
                    img, _ = sprite
                    g.put(canvas, img, (W - img.width) / 2, self.style.caption_y - img.height / 2)
                    break
        return canvas
