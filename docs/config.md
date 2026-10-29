# project.toml reference

Each video lives in its own project folder:

```
projects/my-video/
  project.toml        settings and storyboard (this file)
  script.txt          what the avatar says
  prompts/
    portrait.txt      text prompt for the face
    broll-background.txt, broll-hook.txt   (optional b-roll prompts)
  output/             everything generated (not committed to git)
```

All paths in `project.toml` are relative to the project folder. Special values:

- `@portrait` — the selected portrait image (`[portrait] selected`)
- `@narration` — `output/audio/narration.wav` from the `voice` step, or the avatar's own audio if that step was skipped

The layout is designed for **1080×1920 (9:16)**, for Instagram Reels, TikTok and YouTube Shorts.

## Generation settings

### `[project]`
| key | meaning |
|---|---|
| `name` | used for the output file name `output/final/<name>.mp4` |

### `[script]`
| key | default | meaning |
|---|---|---|
| `file` | `script.txt` | the narration. Keep it short: ~2.5 words per second, so 90 words ≈ 36 s |
| `language` | `en` | language code for the transcription step |

### `[portrait]`
| key | default | meaning |
|---|---|---|
| `model` | `openai/gpt-image-2.5-sunburst` | any OpenRouter image model that supports `aspect_ratio` |
| `prompt_file` | `prompts/portrait.txt` | |
| `aspect_ratio` | `9:16` | keep 9:16 so the photo matches the video |
| `quality` | `high` | `low` / `medium` / `high` / `xhigh` / `max` |
| `selected` | `""` | set with `portrait --select <file>` |

A portrait that animates well: front-facing, eyes to camera, closed-mouth smile, soft even light, whole face, jawline and ears visible, hands out of frame, simple background.

### `[voice]`
| key | default | meaning |
|---|---|---|
| `tts_models` | free HeyGen Voice Turbo, then the paid one | tried in order by the `voice` step |
| `voice` | `nadine` | HeyGen default voices: nadine, tabitha, bram, gareth, noelle, meredith, sabrina, lucian, weston, vincent |
| `heygen_voice_id` | Nadine's ID | the same voice for Avatar IV. If you change `voice`, look up the matching ID in HeyGen's voice docs |

### `[avatar]`
| key | default | meaning |
|---|---|---|
| `model` | `heygen/avatar-iv` | |
| `resolution` | `1080p` | |
| `key_color` | `#00FF00` | Avatar IV removes the photo background and renders on this color, which is keyed out later. Avoid this color in clothes and hair |
| `expressiveness` | `""` | `low` (HeyGen default), `medium`, `high` |
| `motion_prompt` | `""` | e.g. "nods occasionally, small hand gestures" |
| `price_per_second` | `0.05` | used for the cost estimate only |

### `[framing]`
Where the face sits in the avatar video. Check it with `python -m avatar_reel framing -p <project>`.

| key | default | meaning |
|---|---|---|
| `split_scale` | `0.55` | size of the avatar in `split` scenes |
| `split_top` | `904` | y position of the avatar in `split` scenes |
| `feather_top`, `feather_ramp` | `1400`, `90` | where the shoulders fade into the background in `split` scenes |
| `circle_crop` | `[940, 940, 70, 160]` | `[w, h, x, y]` square around the head for `pip` scenes. Head top to chin must fit |
| `compare_crop` | `[600, 900, 240, 140]` | `[w, h, x, y]` region for the `compare` scene (2:3 ratio) |

### `[captions]`
| key | default | meaning |
|---|---|---|
| `max_chars`, `max_words` | `24`, `4` | caption chunk size |
| `keep_together` | `[]` | word pairs that must not be split across captions, e.g. `[["Avatar", "IV"]]` |
| `highlight` | `[]` | words drawn in the accent color |
| `[captions.aliases]` | | spellings the transcriber may use for script words, e.g. `heijen = "heygen"` |

### `[ambient]` and `[hook]` (optional AI b-roll)
| key | ambient default | hook default | meaning |
|---|---|---|---|
| `model` | `google/veo-3.1-lite` | same | |
| `prompt_file` | `prompts/broll-background.txt` | `prompts/broll-hook.txt` | |
| `duration` | `8` | `4` | seconds generated (Veo: 4, 6 or 8) |
| `negative_prompt` | | | things to avoid |
| `opacity` | `0.45` | | how strongly the ambient clip shows over the gradient |
| `end` | | `1.6` | the hook covers `0..end` s. Choose a pause in the speech. The hook ends exactly on the avatar frame at this time |
| `trim` | | `[0.4, 3.4]` | part of the generated clip that is used, sped up to fill `0..end` |
| `person_generation` | | `allow_adult` | needed because the hook's last frame shows a person |

A clip is used whenever `output/broll/ambient.mp4` or `output/broll/hook.mp4` exists. To leave one out of a render, pass `--no-ambient` or `--no-hook`. The ambient clip appears only in `full` scenes. It is blurred, desaturated and ping-pong looped.

### `[cover]`
| key | default | meaning |
|---|---|---|
| `title` | | list of lines |
| `subtitle` | `""` | small pill under the title |
| `avatar_at`, `hook_at` | `1.6`, `2.0` | which moment to use for cover A (avatar) and cover B (hook) |

### `[style]`
Colors as `"#RRGGBB"`: `bg_top`, `bg_bottom`, `ink`, `muted`, `accent`, `accent_soft`, `white`, `code_bg`, `line`, `bar_idle`. Also `caption_y`, which is the vertical center of the captions (default 1460).

Fonts go in `[style.fonts]` with the roles `black`, `heavy`, `bold`, `medium`, `mono`, `mono_bold`, given as file names (searched in `assets/fonts/` and the system font folders) or absolute paths.

## Storyboard: `[[scenes]]`

Scenes run in order. Each scene lasts until the next one starts.

| key | meaning |
|---|---|
| `layout` | `full`: avatar full screen. `split`: card on top, avatar below. `pip`: card plus avatar in a circle. `compare`: input photo next to the output video |
| `start` | a phrase from the script (the scene starts when it is spoken) or a number of seconds. Ignored for the first scene |
| `lead` | seconds before the phrase (default `0.05`) |

### Triggers (`at`)
Every element can have `at`. It can be a **phrase**, which triggers the first time that phrase is spoken inside the scene, or a **number of seconds** from the start of the video. Without `at`, the element appears when the scene starts. Phrases are matched word by word, ignoring case and punctuation.

### `[scenes.card]` (for `split` and `pip`)
| key | meaning |
|---|---|
| `step` | small chip, e.g. `"STEP 1"` |
| `title` | card heading |
| `height` | optional fixed height. By default it is computed from the blocks |

Blocks are stacked top to bottom in `[[scenes.card.blocks]]`:

| `type` | keys | what it shows |
|---|---|---|
| `code` | `label`, `text` or `text_file`, `type_seconds` (3.2), `delay` (0.5), `height` (470) | an editor window with typewriter text |
| `media` | `image`, `tag`, `title`, `subtitle`, `lines` (list), `height` (470) | an image with a spec column |
| `quote` | `text`, `label`, `size` (36) | a paragraph |
| `waveform` | `audio` (`@narration`), `bars` (64), `height` (200) | audio bars that fill with color as the scene plays |
| `flow` | `inputs` (list of `{image=…, at=…}` or `{tile="label", sub="…", at=…}`), `model`, `model_at`, `arrow_at`, `output`, `output_at` | an inputs → model → output diagram |
| `mono` | `lines` (list), `size` (25) | small monospace lines, e.g. the API endpoint |

Add `replace = true` together with `at` to a block to make it crossfade into the place of the block above it, as the portrait replaces the prompt in the example.

### `[scenes.pip]`
`tag` (default `● LIVE`) and `note`: the label next to the circle.

### `[scenes.compare]`
`step`, `title`, `image` (`@portrait`), `input_label`, `input_text`, `output_label`, `output_text`.

### `[[scenes.overlays]]` (any layout)
| `type` | keys |
|---|---|
| `badge` | `text`, `style`, `at`, `y` (1150), `size` (42) |
| `pills` | `items` (list of `{text, style, at}`), `y` (1150), `size` (40), `gap` (18) |

`style` is one of `accent`, `dark`, `light` or `soft`.

Keep important content between y = 270 and y = 1536, and away from the right edge in the lower half. Instagram's interface covers those areas.
