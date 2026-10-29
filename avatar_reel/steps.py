import json
import re
import sys
from datetime import datetime
from pathlib import Path

from . import media
from . import openrouter as api
from .project import H, W

PORTRAIT_PRICE = {"low": 0.01, "medium": 0.01, "high": 0.035, "xhigh": 0.07, "max": 0.14, "auto": 0.035}
WORDS_PER_SECOND = 2.55


def confirm(what, estimate, yes):
    print(f"\n{what}\nEstimated cost: ~${estimate:.2f} (charged to your OpenRouter credits)")
    if yes:
        return
    if not sys.stdin.isatty():
        raise SystemExit("Not confirmed. Rerun with --yes after the user agrees to the cost.")
    if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
        raise SystemExit("Cancelled.")


def dry_run(payload):
    def shorten(value):
        if isinstance(value, str) and value.startswith("data:") and len(value) > 80:
            return value[:60] + f"...<{len(value)} chars>"
        if isinstance(value, dict):
            return {k: shorten(v) for k, v in value.items()}
        if isinstance(value, list):
            return [shorten(v) for v in value]
        return value
    print(json.dumps(shorten(payload), indent=2, ensure_ascii=False))
    print("\n--dry-run: nothing was sent.")


def portrait(project, count=1, quality=None, yes=False, dry=False):
    cfg = project.conf("portrait")
    quality = quality or cfg["quality"]
    payload = {"model": cfg["model"], "prompt": " ".join(project.path(cfg["prompt_file"]).read_text().split()),
               "aspect_ratio": cfg["aspect_ratio"], "quality": quality}
    if dry:
        return dry_run(payload)
    confirm(f"Generate {count} portrait(s) with {cfg['model']} (quality={quality}).",
            PORTRAIT_PRICE.get(quality, 0.05) * count, yes)
    out_dir = project.out_dir("portraits")
    saved = []
    for n in range(count):
        images, cost = api.generate_image(payload)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for i, (data, mime) in enumerate(images):
            path = out_dir / f"portrait-{stamp}-{n}{i}.{mime.split('/')[-1].replace('jpeg', 'jpg')}"
            path.write_bytes(data)
            saved.append(path)
            print(f"Saved {path} (cost: ${cost})")
    print("\nLook at the images, then pick one with: portrait --select <file>")
    return saved


def select_portrait(project, path):
    path = Path(path).resolve()
    if not path.exists():
        raise SystemExit(f"{path} not found")
    try:
        value = str(path.relative_to(project.root))
    except ValueError:
        value = str(path)
    project.set_value("portrait", "selected", value)
    print(f"Selected portrait: {value}")


def voice(project):
    cfg = project.conf("voice")
    text = project.script_text
    for model in cfg["tts_models"]:
        print(f"Trying {model} (voice={cfg['voice']})...")
        result, error = api.speech(model, text, cfg["voice"])
        if result:
            break
        print(f"  failed: {error}")
    else:
        raise SystemExit("All TTS models failed.")
    if not model.endswith(":free"):
        print(f"Note: {model} is a paid model (a few cents for a short script).")
    pcm, rate, channels = result
    out = project.narration
    out.parent.mkdir(parents=True, exist_ok=True)
    pcm_path = out.with_suffix(".pcm")
    pcm_path.write_bytes(pcm)
    media.pcm_to_wav(pcm_path, out, rate, channels)
    pcm_path.unlink()
    print(f"Saved {out} ({len(pcm) / (rate * channels * 2):.1f}s, {rate} Hz) using {model}")
    return out


def first_sentences(text, min_words=10):
    words = text.split()
    for i, word in enumerate(words, 1):
        if i >= min_words and re.search(r"[.!?]$", word):
            return " ".join(words[:i])
    return " ".join(words[:min_words])


def avatar(project, test=False, yes=False, dry=False, resume=None):
    cfg = project.conf("avatar")
    text = first_sentences(project.script_text) if test else project.script_text
    out = project.out / "avatar" / ("avatar-test.mp4" if test else "avatar.mp4")
    payload = None
    if not resume:
        heygen = {"voice_id": project.conf("voice")["heygen_voice_id"], "remove_background": True,
                  "background": {"type": "color", "value": cfg["key_color"]}}
        if cfg["expressiveness"]:
            heygen["expressiveness"] = cfg["expressiveness"]
        if cfg["motion_prompt"]:
            heygen["motion_prompt"] = cfg["motion_prompt"]
        payload = {
            "model": cfg["model"], "resolution": cfg["resolution"], "aspect_ratio": cfg["aspect_ratio"],
            "prompt": text,
            "input_references": [{"type": "image_url", "image_url": {"url": api.data_url(project.portrait)}}],
            "provider": {"options": {"heygen": {**heygen, "parameters": dict(heygen)}}},
        }
        if dry:
            return dry_run(payload)
        seconds = len(text.split()) / WORDS_PER_SECOND
        confirm(f"Generate a {'TEST ' if test else ''}talking avatar video (~{seconds:.0f}s) with {cfg['model']}.",
                seconds * cfg["price_per_second"], yes)
    video, _ = api.run_video_job(payload, out, resume=resume)
    if not test:
        transcribe(project)
    return video


def transcribe(project, video=None):
    video = Path(video) if video else project.avatar_video
    wav = media.extract_audio(video, video.with_suffix(".wav"))
    result = api.transcribe(wav, project.conf("transcribe")["model"], project.conf("script")["language"])
    out = video.with_suffix(".words.json")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Transcript: {result['text'].strip()}")
    print(f"Saved word timings to {out} (cost: ${result.get('usage', {}).get('cost')})")
    return out


def broll_payload(project, cfg, first=None, last=None):
    payload = {"model": cfg["model"], "prompt": " ".join(project.path(cfg["prompt_file"]).read_text().split()),
               "aspect_ratio": "9:16", "resolution": cfg["resolution"], "duration": cfg["duration"],
               "generate_audio": False}
    frames = []
    if first:
        frames.append({"type": "image_url", "image_url": {"url": api.data_url(first)}, "frame_type": "first_frame"})
    if last:
        frames.append({"type": "image_url", "image_url": {"url": api.data_url(last)}, "frame_type": "last_frame"})
    if frames:
        payload["frame_images"] = frames
    params = {}
    if cfg.get("negative_prompt"):
        params["negativePrompt"] = cfg["negative_prompt"]
    if frames and cfg.get("person_generation"):
        params["personGeneration"] = cfg["person_generation"]
    if params:
        payload["provider"] = {"options": {"google-vertex": {"parameters": params}}}
    return payload


def ambient(project, yes=False, dry=False, resume=None):
    cfg = project.conf("ambient")
    payload = None if resume else broll_payload(project, cfg)
    if dry:
        return dry_run(payload)
    if not resume:
        confirm(f"Generate a {cfg['duration']}s ambient background with {cfg['model']}.",
                cfg["duration"] * cfg["price_per_second"], yes)
    return api.run_video_job(payload, project.ambient_src, resume=resume)[0]


def hook_frames(project):
    from .render import build_static_assets
    build_static_assets(project)
    broll = project.out_dir("broll")
    background = project.bg_png
    if project.ambient_src.exists():
        media.build_ambient(project.ambient_src, project.bg_png, project.ambient_loop,
                            project.conf("ambient")["opacity"], project.fps, W, H)
        background = project.ambient_loop
    first, last = broll / "hook-firstframe.png", broll / "hook-lastframe.png"
    media.first_frame(background, first)
    media.composite_frame(project.avatar_video, background, project.conf("hook")["end"], last, project.fps,
                          project.conf("avatar")["key_color"])
    print(f"Saved {first} and {last}")
    return first, last


def hook(project, yes=False, dry=False, resume=None):
    cfg = project.conf("hook")
    payload = None
    if not resume:
        if not project.avatar_video.exists():
            raise SystemExit("The hook needs the avatar video first (run `avatar`).")
        first, last = hook_frames(project)
        payload = broll_payload(project, cfg, first, last)
        if dry:
            return dry_run(payload)
        confirm(f"Generate a {cfg['duration']}s opening hook with {cfg['model']} "
                f"(ends exactly on the avatar frame at {cfg['end']}s).", cfg["duration"] * cfg["price_per_second"], yes)
    return api.run_video_job(payload, project.hook_src, resume=resume)[0]


def status(project=None):
    key = api.key_info()
    credit = api.credits()
    print(f"Key usage: ${key['usage']:.2f}" + (f" of ${key['limit']:.2f} limit" if key.get("limit") else "")
          + (f", expires {key['expires_at']}" if key.get("expires_at") else ""))
    print(f"Account balance: ${credit['total_credits'] - credit['total_usage']:.2f} "
          f"(purchased ${credit['total_credits']:.2f}, used ${credit['total_usage']:.2f})")
    if project:
        steps = [("portrait selected", bool(project.conf("portrait")["selected"])),
                 ("narration.wav", project.narration.exists()),
                 ("avatar.mp4", project.avatar_video.exists()),
                 ("avatar.words.json", project.avatar_words.exists()),
                 ("broll/ambient.mp4", project.ambient_src.exists()),
                 ("broll/hook.mp4", project.hook_src.exists())]
        print(f"\nProject {project.name}:")
        for name, done in steps:
            print(f"  [{'x' if done else ' '}] {name}")
