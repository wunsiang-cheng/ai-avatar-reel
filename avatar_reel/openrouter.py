import base64
import json
import mimetypes
import os
import time
from pathlib import Path

import requests

API = "https://openrouter.ai/api/v1"


def load_env(*dirs):
    for directory in dirs:
        env = Path(directory) / ".env"
        if not env.exists():
            continue
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not set. Copy .env.example to .env and put your key in it.")
    return key


def headers():
    return {"Authorization": f"Bearer {api_key()}"}


def data_url(path):
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(Path(path).read_bytes()).decode()}"


def check(resp, what):
    if resp.status_code not in (200, 202):
        raise SystemExit(f"{what} failed ({resp.status_code}): {resp.text[:1000]}")
    return resp


def key_info():
    return check(requests.get(f"{API}/key", headers=headers(), timeout=30), "Key info").json()["data"]


def credits():
    return check(requests.get(f"{API}/credits", headers=headers(), timeout=30), "Credits").json()["data"]


def generate_image(payload):
    resp = check(requests.post(f"{API}/images", headers=headers(), json=payload, timeout=600), "Image generation")
    result = resp.json()
    images = [(base64.b64decode(i["b64_json"]), i.get("media_type", "image/png")) for i in result["data"]]
    return images, result.get("usage", {}).get("cost")


def speech(model, text, voice):
    resp = requests.post(f"{API}/audio/speech", headers=headers(), timeout=600,
                         json={"model": model, "input": text, "voice": voice, "response_format": "pcm"})
    if resp.status_code != 200:
        return None, f"{resp.status_code} {resp.text[:300]}"
    rate, channels = 24000, 1
    for part in resp.headers.get("Content-Type", "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == "rate":
            rate = int(value)
        elif key == "channels":
            channels = int(value)
    return (resp.content, rate, channels), None


def transcribe(path, model, language="en"):
    path = Path(path)
    payload = {
        "model": model,
        "input_audio": {"data": base64.b64encode(path.read_bytes()).decode(), "format": path.suffix.lstrip(".")},
        "language": language,
        "response_format": "verbose_json",
        "timestamp_granularities": ["segment", "word"],
    }
    return check(requests.post(f"{API}/audio/transcriptions", headers=headers(), json=payload, timeout=300),
                 "Transcription").json()


def run_video_job(payload, out_path, resume=None, poll_interval=15, log=print):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    job_file = out_path.with_suffix(".job.json")
    if resume:
        job_id = resume
    else:
        job = check(requests.post(f"{API}/videos", headers=headers(), json=payload, timeout=180),
                    "Video submit").json()
        job_id = job["id"]
        job_file.write_text(json.dumps(job, indent=2))
        log(f"Submitted job {job_id} (saved to {job_file}). If this gets interrupted, rerun with --resume {job_id}")

    start = time.time()
    while True:
        job = check(requests.get(f"{API}/videos/{job_id}", headers=headers(), timeout=60), "Video poll").json()
        status = job["status"]
        log(f"  [{time.time() - start:5.0f}s] {status}")
        if status == "completed":
            break
        if status in ("failed", "cancelled", "expired"):
            job_file.write_text(json.dumps(job, indent=2))
            raise SystemExit(f"Video job {status}: {job.get('error')}")
        time.sleep(poll_interval)

    job_file.write_text(json.dumps(job, indent=2))
    video = check(requests.get(f"{API}/videos/{job_id}/content", params={"index": 0}, headers=headers(),
                               timeout=600), "Video download")
    out_path.write_bytes(video.content)
    cost = job.get("usage", {}).get("cost")
    note = f"original job cost ${cost}; resuming does not charge again" if resume else f"cost ${cost}"
    log(f"Saved {out_path} ({note})")
    return out_path, job
