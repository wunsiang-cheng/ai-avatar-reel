import difflib
import re

NUMBER_WORDS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
                "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten"}


def make_norm(aliases=None):
    aliases = {k.lower(): v.lower() for k, v in (aliases or {}).items()}

    def norm(token):
        t = re.sub(r"[^a-z0-9.]", "", token.lower()).strip(".")
        t = aliases.get(t, t)
        return aliases.get(NUMBER_WORDS.get(t, t), NUMBER_WORDS.get(t, t))

    return norm


def align(tokens, words, norm):
    a = [norm(t) for t in tokens]
    b = [norm(w["word"]) for w in words]
    times = [None] * len(a)
    for block in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            w = words[block.b + k]
            times[block.a + k] = (w["start"], w["end"])
    i = 0
    while i < len(a):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(a) and times[j] is None:
            j += 1
        t0 = times[i - 1][1] if i > 0 else 0.0
        t1 = times[j][0] if j < len(a) else t0 + 0.4 * (j - i)
        step = (t1 - t0) / (j - i)
        for k in range(i, j):
            times[k] = (t0 + step * (k - i), t0 + step * (k - i + 1))
        i = j
    return times


class Timeline:
    def __init__(self, script_text, words, aliases=None):
        self.norm = make_norm(aliases)
        self.tokens = script_text.split()
        self.times = align(self.tokens, words, self.norm)

    def find(self, phrase, after=0.0):
        target = [self.norm(t) for t in phrase.split()]
        normed = [self.norm(t) for t in self.tokens]
        for i in range(len(normed) - len(target) + 1):
            if normed[i:i + len(target)] == target and self.times[i][0] >= after - 1e-6:
                return self.times[i][0], self.times[i + len(target) - 1][1]
        raise SystemExit(f'Phrase "{phrase}" not found in the script after {after:.2f}s. '
                         f"Check the trigger in project.toml.")

    def resolve(self, at, after=0.0, lead=0.1):
        if at is None:
            return None
        if isinstance(at, (int, float)):
            return float(at)
        return self.find(at, after)[0] - lead


def caption_chunks(timeline, keep_together=(), max_chars=24, max_units=4):
    tokens, times, norm = timeline.tokens, timeline.times, timeline.norm
    pairs = {(norm(a), norm(b)) for a, b in keep_together}
    units = []
    for i, tok in enumerate(tokens):
        if units and (norm(tokens[i - 1]), norm(tok)) in pairs:
            units[-1].append(i)
        else:
            units.append([i])

    def text(unit_list):
        return " ".join(tokens[k] for u in unit_list for k in u)

    groups, cur = [], []
    for n, unit in enumerate(units):
        cur.append(unit)
        nxt = units[n + 1] if n + 1 < len(units) else None
        if nxt is None or tokens[unit[-1]][-1] in ".,:!?":
            groups.append(cur)
            cur = []
            continue
        ends_sentence = tokens[nxt[-1]][-1] in ".,:!?"
        limit = max_chars + 4 if ends_sentence else max_chars
        if len(cur) >= max_units + ends_sentence or len(text(cur + [nxt])) > limit:
            groups.append(cur)
            cur = []
    chunks = []
    for n, group in enumerate(groups):
        idx = [k for u in group for k in u]
        start = times[idx[0]][0]
        end = times[idx[-1]][1] + 0.35
        if n + 1 < len(groups):
            end = min(end, times[groups[n + 1][0][0]][0])
        chunks.append((start, end, [tokens[k] for k in idx]))
    return chunks
