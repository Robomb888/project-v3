import re
import unicodedata
 
_CHAR_MAP = {
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-",
    "\u2026": "...",
    "\u200b": "", "\ufeff": "",
}
 
def clean_text_old(text):
    text = unicodedata.normalize("NFKC", text)
    for bad, good in _CHAR_MAP.items():
        text = text.replace(bad, good)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)              # collapse spaces/tabs, keep newlines
    text = re.sub(r" *\n *", "\n", text)               # trim spaces around newlines
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)       # rejoin hyphenated line-wraps
    text = re.sub(r"(?<=[^\n.!?:])\n(?=[a-z])", " ", text)  # join soft mid-sentence wraps
    text = re.sub(r"\n{3,}", "\n\n", text)             # at most one blank line
    return text.strip()


def clean_text(text):
    text = unicodedata.normalize("NFKC", text)
    for bad, good in _CHAR_MAP.items():
        text = text.replace(bad, good)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)          # collapse spaces/tabs, keep newlines
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)   # rejoin hyphenated line-wraps

    lines = [ln.strip() for ln in text.split("\n")]
    segments = []
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        if not ln:
            i += 1
            continue

        # A line ending in ":" introduces a list (e.g. "Diagnoses:"). Collapse the
        # introducer plus the following non-blank lines into ONE segment, so a list
        # of diagnoses reads as a single sentence. The list ends at a blank line.
        if ln.endswith(":") or ln.endswith(";"):
            items = []
            i += 1
            while i < n and lines[i]:
                items.append(lines[i].rstrip(" ."))
                i += 1
            segments.append(f"{ln} " + "; ".join(items) if items else ln)
            continue

        # Otherwise build a prose run: pull in soft-wrapped continuation lines (the
        # next line continues the sentence -- starts lowercase or a digit -- and the
        # current line did not already end a sentence). A capitalized next line (a
        # new address line, greeting, or sentence) ends the run.
        run = [ln]
        i += 1
        while (i < n and lines[i]
               and (lines[i][0].islower() or lines[i][0].isdigit())
               and not run[-1].endswith((".", "!", "?"))):
            run.append(lines[i])
            i += 1
        segments.append(" ".join(run))

    return "\n".join(segments).strip()