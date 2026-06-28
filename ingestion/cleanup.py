import re
import unicodedata
 
_CHAR_MAP = {
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-",
    "\u2026": "...",
    "\u200b": "", "\ufeff": "",
}
 
def clean_text(text):
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