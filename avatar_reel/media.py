import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

REQUIRED_FILTERS = ["chromakey", "despill", "alphaextract", "alphamerge", "erosion", "gblur", "overlay",
                    "loudnorm", "colorchannelmixer", "reverse", "concat"]


def require_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            raise SystemExit(f"{tool} not found. Install ffmpeg (https://ffmpeg.org/download.html).")


def missing_filters():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    names = {line.split()[1] for line in out.splitlines() if len(line.split()) > 2}
    return [f for f in REQUIRED_FILTERS if f not in names]


def run(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + [str(a) for a in args], check=True)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def frame_count(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                          "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


def key_hex(color):
    return "0x" + color.lstrip("#").upper()


def key_filters(src, out, key_color="#00FF00"):
    return [
        f"{src}format=rgba,split=2[kc_{out}][km_{out}]",
        f"[km_{out}]format=yuva444p,chromakey={key_hex(key_color)}:0.22:0.06,alphaextract,format=gray,erosion,"
        f"gblur=sigma=0.8[ka_{out}]",
        f"[kc_{out}]despill=type=green:mix=0.5:expand=0[kd_{out}]",
        f"[kd_{out}][ka_{out}]alphamerge,format=rgba[{out}]",
    ]


def select_frame(frame):
    return f"select=eq(n\\,{frame}),setpts=N/TB,"


def extract_audio(video, out, rate=44100):
    run(["-i", video, "-vn", "-ac", "1", "-ar", rate, out])
    return Path(out)


def pcm_to_wav(pcm_path, wav_path, rate, channels):
    run(["-f", "s16le", "-ar", rate, "-ac", channels, "-i", pcm_path, wav_path])


def keyed_frame(video, seconds, out, fps, key_color):
    graph = ";".join(key_filters(f"[0:v]{select_frame(round(seconds * fps))}", "k", key_color))
    run(["-i", video, "-filter_complex", graph, "-map", "[k]", "-frames:v", 1, out])
    return Image.open(out).convert("RGBA")


def composite_frame(video, background, seconds, out, fps, key_color):
    frame = round(seconds * fps)
    bg_input = ["-i", background] if Path(background).suffix == ".mp4" else ["-loop", 1, "-i", background]
    bg_select = select_frame(frame) if Path(background).suffix == ".mp4" else ""
    graph = ";".join(key_filters(f"[0:v]{select_frame(frame)}", "k", key_color) + [
        f"[1:v]{bg_select}format=rgba[b]",
        "[b][k]overlay=format=auto",
    ])
    run(["-i", video, *bg_input, "-filter_complex", graph, "-frames:v", 1, out])


def first_frame(video, out):
    run(["-i", video, "-frames:v", 1, out])


def build_ambient(src, bg_png, out, opacity, fps, w, h):
    graph = ";".join([
        f"[0:v]fps={fps},scale={w}:{h},gblur=sigma=28,eq=saturation=0.55:brightness=0.03,split[f][r0]",
        "[r0]reverse[r]",
        f"[f][r]concat=n=2:v=1:a=0,format=rgba,colorchannelmixer=aa={opacity}[amb]",
        "[1:v]format=rgba[g]",
        "[g][amb]overlay=shortest=1,format=yuv420p[out]",
    ])
    run(["-i", src, "-loop", 1, "-framerate", fps, "-i", bg_png, "-filter_complex", graph, "-map", "[out]", "-an",
         "-c:v", "libx264", "-crf", 14, "-pix_fmt", "yuv420p", out])


def build_hook(src, out, trim, end, fps, w, h):
    start, stop = trim
    stop = min(stop, duration(src))
    factor = end / (stop - start)
    run(["-i", src, "-vf", f"trim={start}:{stop},setpts=(PTS-STARTPTS)*{factor:.6f},fps={fps},"
         f"scale={w}:{h}:flags=lanczos", "-an", "-c:v", "libx264", "-crf", 14, "-pix_fmt", "yuv420p", out])


def frame_at(video, seconds, out, width=None):
    vf = ["-vf", f"scale={width}:-1"] if width else []
    run(["-ss", seconds, "-i", video, "-frames:v", 1, *vf, out])
    return Image.open(out)


def contact_sheet(video, times, out, tmp_dir, columns=5, width=360):
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for k, t in enumerate(times):
        frames.append((t, frame_at(video, t, tmp_dir / f"sheet-{k}.png", width).convert("RGB")))
    rows = (len(frames) + columns - 1) // columns
    fw, fh = frames[0][1].size
    label = 34
    sheet = Image.new("RGB", (columns * fw + (columns + 1) * 10, rows * (fh + label + 10) + 10), "white")
    draw = ImageDraw.Draw(sheet)
    for k, (t, img) in enumerate(frames):
        x = 10 + (k % columns) * (fw + 10)
        y = 10 + (k // columns) * (fh + label + 10)
        draw.text((x, y + 6), f"{t:.1f}s", fill=(28, 31, 38))
        sheet.paste(img, (x, y + label))
    sheet.save(out)
    for k in range(len(frames)):
        (tmp_dir / f"sheet-{k}.png").unlink(missing_ok=True)
    return out
