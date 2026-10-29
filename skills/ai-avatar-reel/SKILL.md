---
name: ai-avatar-reel
description: Make a short vertical video (Instagram Reel, YouTube Short, TikTok) of an AI-generated person talking, using the ai-avatar-reel repo and one OpenRouter API key. Covers the portrait (GPT Image), the voice (HeyGen Voice), the lip-synced video (HeyGen Avatar IV), optional AI b-roll (Veo), captions and cards, and the cover image. Use when the user asks for an AI avatar, AI presenter, talking-head or "digital human" video, even without technical words.
---

# AI avatar reel

You are helping someone who may not be technical make a 20–60 second vertical video of an AI-generated person speaking their script. You run the commands; the user makes the creative decisions and approves every cost. Talk to the user in their language and avoid jargon. Explain what each step does in one or two sentences.

The tool is the `ai-avatar-reel` repository: a Python package run with `python -m avatar_reel <command> -p <project folder>`. Run every command from the repository root. The option reference is `docs/config.md`, and a complete working project is `projects/example/project.toml`. Read both before you edit a storyboard.

## Ground rules

1. **Money.** Commands marked *paid* spend the user's OpenRouter credits. Before each one, tell the user what it does and the estimated cost, and wait for an explicit yes. Only then run it with `--yes`. Without `--yes` the tool refuses to spend in a non-interactive shell. To show a request without spending, use `--dry-run`.
2. **API key.** Never ask the user to paste the key into the chat, and never print `.env`. Ask them to create `.env` themselves, starting from `.env.example`.
3. **Real people.** Don't make an avatar of a real, identifiable person, or clone a real voice, unless the user confirms that person consented. Default to a fictional person.
4. **Disclosure.** Remind the user to label the post as AI-generated. Instagram has an "AI info" label.
5. **One step at a time.** Finish a step, show the result, get approval, then continue. Don't chain paid steps.
6. **Interrupted jobs.** If a video job is interrupted, rerun the same command with `--resume <job id>`. The ID is printed and saved in `output/.../*.job.json`, and resuming doesn't charge again. Never resubmit a job you could resume.

## Costs (OpenRouter prices at the time of writing; the tool prints its own estimate)

| step | command | cost |
|---|---|---|
| portrait, quality high | `portrait` | ~$0.035 per image (medium ~$0.01) |
| narration | `voice` | free until 2026-11-30 (free HeyGen tier), then a few cents |
| lip-sync test, first sentence | `avatar --test` | ~$0.30 |
| full talking video | `avatar` | $0.05 per second (36 s ≈ $1.80) |
| word timings | runs inside `avatar` | < $0.01 |
| ambient background | `broll ambient` | ~$0.24 |
| opening "materialize" hook | `broll hook` | ~$0.12 |
| framing, render, sheet, cover, status, check | | free (local) |

A typical video costs $2–3 including one test. Suggest at least $5 of credit. Check the balance with `status`. A key's `limit` is a spending cap, not money in the account.

## Workflow

### 0. Setup (once)
```bash
pip install -r requirements.txt
python -m avatar_reel check
```
Fix everything marked `!!`:
- ffmpeg missing: install it, e.g. `brew install ffmpeg`, `sudo apt install ffmpeg` or `winget install ffmpeg`.
- Fonts missing: install Lato and DejaVu Sans Mono, or put the `.ttf` files in `assets/fonts/`.
- Key missing: the user copies `.env.example` to `.env` and pastes their key there themselves.

### 1. Interview
Ask briefly, and offer defaults:
- **What is the video about, and for which platform?** Default: Instagram Reel, 9:16.
- **Who is the presenter?** Age, look, clothes, setting. Default: a friendly creator in a neutral sweater, in a bright, simple room.
- **Language.** The built-in voices are English. If the user needs another language, say that this hasn't been tested and suggest a short `avatar --test` first.
- **Length.** 20–45 s works best, at about 2.5 words per second.
- **Extras.** The AI background and opening hook are optional, cost about $0.36 together, and add polish. Default: decide later.

### 2. Create the project and write the script
```bash
python -m avatar_reel init projects/<short-name>
```
Write `projects/<name>/script.txt`. Spoken English, short sentences. Hook the viewer in the first sentence. Keep names consistent. Count the words: seconds × 2.5. Show the script to the user and revise until they approve. Changing the script after the `avatar` step means paying for the video again, so get a firm approval here.

### 3. Portrait (paid)
Write `prompts/portrait.txt` from the interview. Keep the technical part of the example prompt, because it is what makes the face animate well: front-facing, eyes to camera, closed-mouth smile, soft even light, whole face, jawline and ears visible, hands out of frame, simple slightly blurred background, no text.
```bash
python -m avatar_reel portrait -p P -n 2 --yes        # after approval
```
If you can view images, check the candidates against that list. Show the user the file paths, or tell them to open the files. After they choose:
```bash
python -m avatar_reel portrait -p P --select P/output/portraits/<file>
```
Each generation is a new person. The chosen image *is* the avatar from now on.

### 4. Narration (free)
```bash
python -m avatar_reel voice -p P
```
This is optional, but the `waveform` card uses it. If the user wants a voice other than `nadine`, set `[voice] voice` and also `heygen_voice_id` to the same voice's HeyGen ID. Avatar IV uses the ID.

### 5. Lip-sync test (paid, ~$0.30), then the full video (paid)
```bash
python -m avatar_reel avatar -p P --test --yes
python -m avatar_reel sheet -p P --video P/output/avatar/avatar-test.mp4 --times 0.5 1.5 2.5 3.5 4.5
```
Ask the user to watch `output/avatar/avatar-test.mp4` and judge the mouth, voice and expression. When they are happy:
```bash
python -m avatar_reel avatar -p P --yes      # takes about 5 minutes for 35 s
```
This also writes the word timings to `output/avatar/avatar.words.json`, which captions and triggers use. To change the energy, set `[avatar] expressiveness = "medium"` *before* this step. The video has a pure green background on purpose; it is removed later.

### 6. Framing check (free)
```bash
python -m avatar_reel framing -p P
```
Look at `output/build/framing.png`. From head top to chin, the face must be inside the red `circle_crop` and the blue `compare_crop` boxes. If it isn't, adjust `[framing]` in `project.toml`: move x and y, or make the boxes bigger. Keep `compare_crop` at a 2:3 ratio.

### 7. Storyboard and render (free, repeat as needed)
Edit the `[[scenes]]` in `projects/<name>/project.toml` so they follow the new script. The example's structure works for most explainers:
1. `full`: hook sentence, with a badge
2–4. `split` or `pip` cards: one card per point, with `step` and `title`, and blocks that show something concrete (code, image, quote, waveform, flow diagram, monospace lines)
5. `compare` (optional): input photo next to the talking result
6. `full`: closing line, with pills

Rules:
- A scene's `start` and an element's `at` must be phrases that appear **in the script**, word for word, ignoring case and punctuation, or numbers of seconds. If a phrase isn't found, the render stops with a clear error.
- Remove example content that no longer fits: the waveform, the portrait media block, the flow labels.
- Update `[captions] highlight` and `keep_together` for the new script's names.
- Update `[cover] title`.

```bash
python -m avatar_reel render -p P
python -m avatar_reel sheet -p P
```
Review `output/final/<name>-sheet.jpg` if you can view images. Check that text is readable, that nothing covers the face, that captions are inside the frame, that no card overlaps the avatar, and that the timing makes sense. Then ask the user to watch `output/final/<name>.mp4` and collect their changes. A render takes about a minute and is free.

### 8. Optional AI b-roll (paid), in this order
```bash
python -m avatar_reel broll ambient -p P --yes    # moving background for full-screen scenes
python -m avatar_reel broll hook -p P --yes       # particles that become the avatar; needs ambient first if you use both
python -m avatar_reel render -p P
```
Make the ambient clip first: the hook's last frame is built from the ambient background, so the cut is seamless. Set `[hook] end` to a pause in the speech, at the end of the first sentence; the word timings are in `avatar.words.json`. To leave either clip out of a render, pass `--no-ambient` or `--no-hook`.

### 9. Cover and post text (free)
```bash
python -m avatar_reel cover -p P
```
`output/cover/cover-preview.jpg` shows each cover as it appears in the Reels player, the profile grid (3:4) and the feed (4:5). Offer to draft the post caption (under 2,200 characters, 3–5 hashtags, no `#` inside technical text) and remind the user about the AI label.

## Troubleshooting

| symptom | fix |
|---|---|
| `402 ... exceeds your available credits` | The account balance is too low. A key's `limit` is not a balance. Ask the user to add credits, then check with `status` |
| `Phrase "..." not found in the script` | Fix that `start` or `at` in `project.toml`, using exact words from `script.txt` |
| captions or triggers a bit off on a word | The transcriber spelled it differently. Add it to `[captions.aliases]`, e.g. `heijen = "heygen"` |
| a green fringe or a green-tinted area | The clothes or hair are close to `key_color`. Choose a portrait without green, or change `key_color` *before* generating the avatar |
| the face is cut off in the circle or the compare card | Adjust `[framing]` and rerun `framing` |
| a video job `failed` | Read the error. A content-policy error usually means the prompt or image needs changing. A failed job is usually not charged; check with `status` |
| Veo rejects the hook | It needs both frames; the tool sends them. If it's rejected for content policy, rephrase `prompts/broll-hook.txt` or skip the hook; the video works without it |
| the script changes after `avatar` | The talking video has to be generated again, at full cost. Confirm with the user first |

## Command reference
`check`, `init DIR`, `status`, `portrait [-n N] [--quality q] [--select FILE]`, `voice`, `avatar [--test] [--resume ID]`, `transcribe [--video FILE]`, `broll ambient|hook [--resume ID]`, `framing [--at s]`, `render [--no-ambient] [--no-hook] [--out FILE]`, `sheet [--video FILE] [--times ...]`, `cover`. Paid commands also accept `--yes` and `--dry-run`. All commands except `check` and `init` need `-p <project>`.
