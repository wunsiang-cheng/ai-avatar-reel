import subprocess
from pathlib import Path

from PIL import Image

from . import graphics as g
from . import media
from .layout import CIRCLE_D, CIRCLE_POS, OUTPUT_POS, OUTPUT_SIZE, Composer, split_box
from .project import H, W


def build_static_assets(project):
    s = project.style
    Image.fromarray(g.gradient(W, H, s.bg_top, s.bg_bottom)).save(project.bg_png)
    g.circle_mask(CIRCLE_D).save(project.build / "mask-circle.png")
    g.rounded_mask(*OUTPUT_SIZE, 20).save(project.build / "mask-output.png")


def prepare(project, ambient=True, hook=True, log=print):
    build_static_assets(project)
    use_ambient = ambient and project.ambient_src.exists()
    use_hook = hook and project.hook_src.exists()
    if use_ambient:
        media.build_ambient(project.ambient_src, project.bg_png, project.ambient_loop,
                            project.conf("ambient")["opacity"], project.fps, W, H)
    if use_hook:
        cfg = project.conf("hook")
        media.build_hook(project.hook_src, project.hook_clip, cfg["trim"], cfg["end"], project.fps, W, H)
    log(f"Ambient background: {'on' if use_ambient else 'off'}, hook: {'on' if use_hook else 'off'}")
    return use_ambient, use_hook


def enable_expr(windows):
    if not windows:
        return "0"
    return "+".join(f"gte(t,{start})*lt(t,{min(end, 1e5)})" for start, end in windows)


def ffmpeg_command(project, composer, n_frames, out, ambient, hook):
    fps = project.fps
    framing = project.conf("framing")
    key = project.conf("avatar")["key_color"]
    soft = "0x%02X%02X%02X" % project.style.accent_soft
    full_on = enable_expr(composer.windows("full"))
    split_w, split_h, split_x, split_y = split_box(framing)
    cw, chh, cx, cy = framing["circle_crop"]
    ow, oh, ox, oy = framing["compare_crop"]

    graph = media.key_filters("[0:v]", "key", key) + [
        "[key]split=4[k1][k2][k3][k4]",
        f"[k2]scale={split_w}:{split_h}[ks]",
        f"color=c={soft}:s={CIRCLE_D}x{CIRCLE_D}:r={fps}[cbg]",
        f"[k3]crop={cw}:{chh}:{cx}:{cy},scale={CIRCLE_D}:{CIRCLE_D}[kc0]",
        "[cbg][kc0]overlay=shortest=1,format=rgba[kc1]",
        "[2:v]format=gray[cm]",
        "[kc1][cm]alphamerge[kc]",
        f"color=c={soft}:s={OUTPUT_SIZE[0]}x{OUTPUT_SIZE[1]}:r={fps}[obg]",
        f"[k4]crop={ow}:{oh}:{ox}:{oy},scale={OUTPUT_SIZE[0]}:{OUTPUT_SIZE[1]}[ko0]",
        "[obg][ko0]overlay=shortest=1,format=rgba[ko1]",
        "[3:v]format=gray[om]",
        "[ko1][om]alphamerge[ko]",
    ]
    if ambient:
        graph += ["[1:v]format=rgba[bg0]", "[5:v]format=rgba[amb]", f"[bg0][amb]overlay=0:0:enable='{full_on}'[bg]"]
    else:
        graph += ["[1:v]format=rgba[bg]"]
    graph += [
        f"[bg][k1]overlay=0:0:enable='{full_on}'[v1]",
        f"[v1][ks]overlay={split_x}:{split_y}:enable='{enable_expr(composer.windows('split'))}'[v2]",
        f"[v2][kc]overlay={CIRCLE_POS[0]}:{CIRCLE_POS[1]}:enable='{enable_expr(composer.windows('pip'))}'[v3]",
        f"[v3][ko]overlay={OUTPUT_POS[0]}:{OUTPUT_POS[1]}:enable='{enable_expr(composer.windows('compare'))}'[v4]",
    ]
    if hook:
        cfg = project.conf("hook")
        graph += [f"[6:v]format=rgba,fade=t=out:st={cfg['end'] - cfg['fade']}:d={cfg['fade']}:alpha=1[hk]",
                  f"[v4][hk]overlay=0:0:enable='lt(t,{cfg['end']})':eof_action=pass[v5]",
                  "[v5][4:v]overlay=0:0:shortest=1,format=yuv420p[vout]"]
    else:
        graph += ["[v4][4:v]overlay=0:0:shortest=1,format=yuv420p[vout]"]
    graph += ["[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]"]

    loop = ["-loop", "1", "-framerate", str(fps), "-i"]
    extra = ["-stream_loop", "-1", "-i", str(project.ambient_loop)] if ambient else ["-f", "lavfi", "-i", "nullsrc"]
    if hook:
        extra += ["-i", str(project.hook_clip)]
    return [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(project.avatar_video),
        *loop, str(project.bg_png),
        *loop, str(project.build / "mask-circle.png"),
        *loop, str(project.build / "mask-output.png"),
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-framerate", str(fps), "-i", "pipe:0",
        *extra,
        "-filter_complex", ";".join(graph),
        "-map", "[vout]", "-map", "[aout]",
        "-frames:v", str(n_frames),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out),
    ]


def render(project, out, ambient=True, hook=True, log=print):
    media.require_ffmpeg()
    if not project.avatar_video.exists():
        raise SystemExit(f"{project.avatar_video} not found. Run the `avatar` step first.")
    use_ambient, use_hook = prepare(project, ambient, hook, log)
    composer = Composer(project, use_hook)
    log("Scenes: " + ", ".join(f"{s.layout}@{s.start:.2f}s" for s in composer.scenes))
    n_frames = media.frame_count(project.avatar_video)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(ffmpeg_command(project, composer, n_frames, out, use_ambient, use_hook),
                            stdin=subprocess.PIPE)
    try:
        for i in range(n_frames):
            proc.stdin.write(composer.frame(i / project.fps).tobytes())
            if i % 100 == 0:
                log(f"  frame {i}/{n_frames}")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed while rendering")
    log(f"Saved {out}")
    return out
