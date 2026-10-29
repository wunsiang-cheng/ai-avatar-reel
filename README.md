# ai-avatar-reel

Make a short vertical video (Reels / Shorts / TikTok) of an **AI-generated person talking**, from a text prompt and a script. Every model call goes through one [OpenRouter](https://openrouter.ai) API key. Editing is done locally with Python and ffmpeg, so you don't need a video editor.

```
prompt ──► portrait (GPT Image 2.5) ──┐
script ──► voice (HeyGen Voice) ──────┼──► talking video (HeyGen Avatar IV, green screen)
                                       │          │
            optional b-roll (Veo 3.1 Lite)         ▼
                                   local compositing: keying, cards, captions, loudness
                                                   │
                                                   ▼
                                   1080×1920 MP4 + cover images
```

The example project in `projects/example` produced a 36-second reel for about **$2.20** in API costs, test runs included, plus **$0.36** for the optional AI b-roll.

## What you need

- Python 3.11 or newer, and `pip install -r requirements.txt`
- [ffmpeg](https://ffmpeg.org/download.html), including `ffprobe`
- The fonts [Lato](https://fonts.google.com/specimen/Lato) and [DejaVu Sans Mono](https://dejavu-fonts.github.io/). Most Linux systems already have them. Elsewhere, install them or drop the `.ttf` files into `assets/fonts/`
- An OpenRouter API key with a few dollars of credit: `cp .env.example .env`, then paste the key into `.env`

Check everything with:

```bash
python -m avatar_reel check
```

## Make a video

```bash
python -m avatar_reel init projects/my-video     # copies the example settings
# edit projects/my-video/script.txt, prompts/portrait.txt and project.toml

P=projects/my-video
python -m avatar_reel portrait   -p $P -n 2               # ~$0.07  two portrait candidates
python -m avatar_reel portrait   -p $P --select projects/my-video/output/portraits/<file>.png
python -m avatar_reel voice      -p $P                    # free*   narration (used for the waveform card)
python -m avatar_reel avatar     -p $P --test             # ~$0.30  first sentence only: check lip-sync
python -m avatar_reel avatar     -p $P                    # ~$0.05/s the full talking video + word timings
python -m avatar_reel framing    -p $P                    # free    check the crop boxes around the face
python -m avatar_reel broll ambient -p $P                 # ~$0.24  optional moving background
python -m avatar_reel broll hook    -p $P                 # ~$0.12  optional "materialize" opening
python -m avatar_reel render     -p $P                    # free    -> output/final/<name>.mp4
python -m avatar_reel sheet      -p $P                    # free    contact sheet for review
python -m avatar_reel cover      -p $P                    # free    cover candidates
python -m avatar_reel status     -p $P                    # credits and progress
```

\* The free HeyGen Voice Turbo tier is available until 2026-11-30. After that, the `voice` step falls back to the paid model, which costs a few cents.

Paid commands print an estimate and ask before spending. `--dry-run` shows the request without sending it, and `--yes` skips the question. If a video job gets interrupted, rerun the same command with `--resume <job id>` (the ID is printed and saved next to the output) to download it without paying again.

The storyboard is defined in `project.toml`: which layout each scene uses, which cards appear, and which spoken word triggers each element. See [docs/config.md](docs/config.md).

## Use it with an AI agent

`skills/ai-avatar-reel/SKILL.md` is a skill for coding agents such as Claude Code or Kimi Code, so someone who doesn't code can just ask their agent to *"make me an AI avatar video about X"*. The agent runs the steps, shows the results and asks before every paid call. Copy the `skills/ai-avatar-reel` folder into your agent's skills directory, or point the agent at the file.

## Things I learned the hard way

- **HeyGen Voice returns raw PCM with no header.** Read the sample rate from the `Content-Type` header (`rate=44100`). When I guessed 24 kHz, the voice played slow and deep.
- **Avatar IV only accepts audio as a public HTTPS URL**, while the photo can be base64. So the avatar speaks the script itself with the same HeyGen voice ID.
- **OpenRouter doesn't expose Avatar IV's transparent WebM output.** Instead I ask for `remove_background` plus a `#00FF00` background and key it out with ffmpeg: chroma key, then despill with `expand=0` (higher values turned a cream sweater pink), then a 1 px alpha erosion.
- **Veo needs both `first_frame` and `last_frame`.** A `last_frame` alone is rejected. Using an empty background as the first frame and the avatar's exact frame as the last makes the cut into the talking video seamless.
- **Captions come from Whisper word timestamps aligned back to the script**, so names like "OpenRouter" or "Avatar IV" are never misspelled or split across two captions.
- **The UI layer is drawn per frame with Pillow** and streamed as raw RGBA into ffmpeg, which does the keying, placement, overlay and `loudnorm` (−14 LUFS) in a single pass.

## Repository layout

```
avatar_reel/     the tool (python -m avatar_reel)
  openrouter.py  API calls: images, speech, transcription, async video jobs
  steps.py       portrait / voice / avatar / transcribe / b-roll steps with cost checks
  layout.py      scenes, cards, overlays, captions (the storyboard engine)
  render.py      ffmpeg filter graph and the render loop
  cover.py       cover images
projects/example the reel from the demo video (settings, prompts, script, notes)
docs/config.md   every project.toml option
skills/          the AI agent skill
```

## Responsible use

The people this makes are synthetic. Label the posts as AI-generated; Instagram has an "AI info" label, for example. Don't use real people's photos or voices without their consent.

## License

[MIT](LICENSE)
