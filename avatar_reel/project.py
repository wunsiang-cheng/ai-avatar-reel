import json
import re
import tomllib
from pathlib import Path

from .graphics import Style

W, H = 1080, 1920

DEFAULTS = {
    "portrait": {"model": "openai/gpt-image-2.5-sunburst", "prompt_file": "prompts/portrait.txt",
                 "aspect_ratio": "9:16", "quality": "high", "selected": ""},
    "voice": {"tts_models": ["heygen/heygen-voice-1-turbo:free", "heygen/heygen-voice-1-turbo"],
              "voice": "nadine", "heygen_voice_id": "83548de556df48ba8c09c42a57c51d85"},
    "script": {"file": "script.txt", "language": "en"},
    "avatar": {"model": "heygen/avatar-iv", "resolution": "1080p", "aspect_ratio": "9:16",
               "key_color": "#00FF00", "expressiveness": "", "motion_prompt": "", "fps": 25,
               "price_per_second": 0.05},
    "framing": {"split_scale": 0.55, "split_top": 904, "feather_top": 1400, "feather_ramp": 90,
                "circle_crop": [940, 940, 70, 160], "compare_crop": [600, 900, 240, 140]},
    "transcribe": {"model": "openai/whisper-large-v3"},
    "captions": {"max_chars": 24, "max_words": 4, "keep_together": [], "highlight": [], "aliases": {}},
    "ambient": {"model": "google/veo-3.1-lite", "prompt_file": "prompts/broll-background.txt",
                "duration": 8, "resolution": "720p", "negative_prompt": "", "opacity": 0.45,
                "price_per_second": 0.03},
    "hook": {"model": "google/veo-3.1-lite", "prompt_file": "prompts/broll-hook.txt",
             "duration": 4, "resolution": "720p", "negative_prompt": "", "person_generation": "allow_adult",
             "end": 1.6, "trim": [0.4, 3.4], "fade": 0.2, "price_per_second": 0.03},
    "cover": {"title": ["I'm not a", "real person."], "subtitle": "", "avatar_at": 1.6, "hook_at": 2.0},
}


def merged(defaults, override):
    out = dict(defaults)
    out.update(override or {})
    return out


class Project:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.config_path = self.root / "project.toml"
        if not self.config_path.exists():
            raise SystemExit(f"{self.config_path} not found. Create a project with: python -m avatar_reel init <dir>")
        self.cfg = tomllib.loads(self.config_path.read_text())
        self.out = self.root / "output"
        self.style = Style.from_config(self.cfg.get("style", {}))
        self.scenes = self.cfg.get("scenes", [])

    def conf(self, name):
        return merged(DEFAULTS[name], self.cfg.get(name))

    @property
    def name(self):
        return self.cfg.get("project", {}).get("name", self.root.name)

    def path(self, rel):
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    def out_dir(self, sub):
        d = self.out / sub
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def fps(self):
        return self.conf("avatar")["fps"]

    @property
    def script_text(self):
        return " ".join(self.path(self.conf("script")["file"]).read_text().split())

    @property
    def portrait(self):
        selected = self.conf("portrait")["selected"]
        if not selected:
            raise SystemExit("No portrait selected. Run `portrait` and then `portrait --select <file>`.")
        path = self.path(selected)
        if not path.exists():
            raise SystemExit(f"Selected portrait not found: {path}")
        return path

    @property
    def avatar_video(self):
        return self.out / "avatar" / "avatar.mp4"

    @property
    def avatar_words(self):
        return self.out / "avatar" / "avatar.words.json"

    @property
    def narration(self):
        return self.out / "audio" / "narration.wav"

    @property
    def build(self):
        return self.out_dir("build")

    @property
    def bg_png(self):
        return self.build / "bg.png"

    @property
    def ambient_src(self):
        return self.out / "broll" / "ambient.mp4"

    @property
    def ambient_loop(self):
        return self.build / "ambient-loop.mp4"

    @property
    def hook_src(self):
        return self.out / "broll" / "hook.mp4"

    @property
    def hook_clip(self):
        return self.build / "hook.mp4"

    def words(self):
        if not self.avatar_words.exists():
            raise SystemExit(f"{self.avatar_words} not found. Run `avatar` (or `transcribe`) first.")
        return json.loads(self.avatar_words.read_text())["words"]

    def asset(self, value):
        if value == "@portrait":
            return self.portrait
        if value == "@narration":
            if self.narration.exists():
                return self.narration
            fallback = self.out / "avatar" / "avatar.wav"
            if not fallback.exists():
                from .media import extract_audio
                extract_audio(self.avatar_video, fallback)
            return fallback
        return self.path(value)

    def set_value(self, section, key, value):
        text = self.config_path.read_text()
        pattern = re.compile(rf"(^\[{re.escape(section)}\][^\[]*?^{re.escape(key)}\s*=\s*)(\"[^\"]*\")", re.M | re.S)
        if pattern.search(text):
            text = pattern.sub(lambda m: m.group(1) + json.dumps(value), text, count=1)
        else:
            header = re.compile(rf"^\[{re.escape(section)}\]\s*$", re.M)
            match = header.search(text)
            if not match:
                text += f"\n[{section}]\n{key} = {json.dumps(value)}\n"
            else:
                text = text[:match.end()] + f"\n{key} = {json.dumps(value)}" + text[match.end():]
        self.config_path.write_text(text)
        self.cfg = tomllib.loads(text)
