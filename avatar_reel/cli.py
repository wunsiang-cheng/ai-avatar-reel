import argparse
import os
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from . import media, steps
from . import openrouter as api
from .graphics import Style, find_font
from .layout import split_box
from .project import Project

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "projects" / "example"


def cmd_check(args):
    ok = True

    def report(good, text, hint=""):
        nonlocal ok
        ok &= good
        print(f"  [{'ok' if good else '!!'}] {text}" + (f"  -> {hint}" if not good and hint else ""))

    print("Environment:")
    report(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}", "Python 3.11 or newer is required")
    has_ffmpeg = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
    report(has_ffmpeg, "ffmpeg / ffprobe", "install ffmpeg")
    if has_ffmpeg:
        missing = media.missing_filters()
        report(not missing, "ffmpeg filters", f"missing: {', '.join(missing)}; install a full ffmpeg build")
    project = Project(args.project) if args.project else None
    fonts = project.style.fonts if project else Style().fonts
    for role, name in fonts.items():
        report(find_font(name) is not None, f"font {name} ({role})", "install Lato / DejaVu Sans Mono or put the file in assets/fonts/")
    has_key = bool(os.environ.get("OPENROUTER_API_KEY"))
    report(has_key, "OPENROUTER_API_KEY", "copy .env.example to .env and add your key")
    if has_key:
        try:
            steps.status(project)
        except SystemExit as e:
            report(False, "OpenRouter API reachable", str(e))
    print("\nAll good." if ok else "\nFix the items marked !! first.")


def cmd_init(args):
    dest = Path(args.dir)
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"{dest} already exists and is not empty")
    shutil.copytree(TEMPLATE, dest, ignore=shutil.ignore_patterns("output", "notes"))
    project = Project(dest)
    project.set_value("portrait", "selected", "")
    project.set_value("project", "name", dest.name)
    print(f"Created {dest}. Next: edit {dest}/script.txt, {dest}/prompts/portrait.txt and {dest}/project.toml")


def cmd_portrait(args):
    project = Project(args.project)
    if args.select:
        return steps.select_portrait(project, args.select)
    steps.portrait(project, args.count, args.quality, args.yes, args.dry_run)


def cmd_framing(args):
    project = Project(args.project)
    framing = project.conf("framing")
    out = project.build / "framing.png"
    img = media.keyed_frame(project.avatar_video, args.at, out, project.fps, project.conf("avatar")["key_color"])
    canvas = Image.new("RGBA", img.size, (225, 228, 234, 255))
    canvas.alpha_composite(img)
    d = ImageDraw.Draw(canvas)
    label_font = project.style.font("black", 36)
    for (w, h, x, y), color, label in [(framing["circle_crop"], (220, 30, 30), "circle_crop"),
                                       (framing["compare_crop"], (30, 90, 230), "compare_crop")]:
        d.rectangle((x, y, x + w, y + h), outline=color, width=6)
        d.text((x + 14, y + h - 50), label, fill=color, font=label_font)
    split_w, split_h, *_ = split_box(framing)
    d.text((20, 20), f"split view shows this frame scaled to {split_w}x{split_h}", fill=(28, 31, 38), font=label_font)
    canvas.convert("RGB").save(out)
    print(f"Saved {out}: the face (head top to chin) must fit inside both boxes. "
          f"Adjust [framing] in project.toml if not.")


def cmd_render(args):
    from .render import render
    project = Project(args.project)
    out = Path(args.out) if args.out else project.out_dir("final") / f"{project.name}.mp4"
    render(project, out, ambient=not args.no_ambient, hook=not args.no_hook)


def cmd_sheet(args):
    project = Project(args.project)
    video = Path(args.video) if args.video else project.out / "final" / f"{project.name}.mp4"
    if not video.exists():
        raise SystemExit(f"{video} not found")
    times = args.times or [round(media.duration(video) * k / 10, 1) for k in range(10)]
    out = video.with_name(video.stem + "-sheet.jpg")
    media.contact_sheet(video, times, out, project.build)
    print(f"Saved {out}")


def cmd_cover(args):
    from .cover import make_covers
    make_covers(Project(args.project))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m avatar_reel",
                                     description="Make a talking AI avatar reel with OpenRouter (HeyGen + friends).")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, func, help_text, project=True, paid=False, resume=False):
        p = sub.add_parser(name, help=help_text, description=help_text)
        if project:
            p.add_argument("-p", "--project", required=True, help="project folder (contains project.toml)")
        if paid:
            p.add_argument("--yes", action="store_true", help="skip the cost confirmation")
            p.add_argument("--dry-run", action="store_true", help="print the request without sending it")
        if resume:
            p.add_argument("--resume", metavar="JOB_ID", help="poll/download an already submitted job (no new cost)")
        p.set_defaults(func=func)
        return p

    p = add("check", cmd_check, "Check Python, ffmpeg, fonts, API key and credits", project=False)
    p.add_argument("-p", "--project", help="optional project folder")

    p = add("init", cmd_init, "Create a new project folder from the example", project=False)
    p.add_argument("dir")

    add("status", lambda a: steps.status(Project(a.project)),
        "Show credits, key usage and which project steps are done")

    p = add("portrait", cmd_portrait, "Generate portrait candidates (paid) or select one", paid=True)
    p.add_argument("-n", "--count", type=int, default=1)
    p.add_argument("--quality", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--select", metavar="FILE", help="use this image as the avatar")

    add("voice", lambda a: steps.voice(Project(a.project)), "Text-to-speech narration (free HeyGen model first)")

    p = add("avatar", lambda a: steps.avatar(Project(a.project), a.test, a.yes, a.dry_run, a.resume),
            "Talking avatar video with HeyGen Avatar IV (paid)", paid=True, resume=True)
    p.add_argument("--test", action="store_true", help="only the first sentence(s), to check quality cheaply")

    p = add("transcribe", lambda a: steps.transcribe(Project(a.project), a.video),
            "Word timestamps for captions (runs automatically after `avatar`)")
    p.add_argument("--video")

    p = add("broll", lambda a: (steps.ambient if a.kind == "ambient" else steps.hook)(
        Project(a.project), a.yes, a.dry_run, a.resume),
        "AI decorative footage: 'ambient' background or opening 'hook' (paid, optional)", paid=True, resume=True)
    p.add_argument("kind", choices=["ambient", "hook"])

    p = add("framing", cmd_framing, "Draw the avatar crop boxes on a frame to check the framing")
    p.add_argument("--at", type=float, default=3.0)

    p = add("render", cmd_render, "Compose the final reel (local, free)")
    p.add_argument("--out")
    p.add_argument("--no-ambient", action="store_true")
    p.add_argument("--no-hook", action="store_true")

    p = add("sheet", cmd_sheet, "Contact sheet of frames from the final video (for review)")
    p.add_argument("--video")
    p.add_argument("--times", type=float, nargs="*")

    add("cover", cmd_cover, "Cover image candidates for the reel (local, free)")

    args = parser.parse_args(argv)
    api.load_env(REPO, Path.cwd(), *([args.project] if getattr(args, "project", None) else []))
    args.func(args)
