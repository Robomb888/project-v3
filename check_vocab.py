"""Verify vocabulary.json agrees with the live FIELD_REGISTRY.
Run from your project root:  python check_vocab.py
"""
import json
from registry import FIELD_REGISTRY


def short_name(fn):
    """'consent.extract' from a function in extractors/consent.py"""
    mod = getattr(fn, "__module__", "").split(".")[-1]
    return f"{mod}.{getattr(fn, '__name__', fn)}"


def check_vocab(vocab_path="vocabulary.json"):
    vocab = json.load(open(vocab_path, encoding="utf-8"))
    reg, voc = set(FIELD_REGISTRY), set(vocab)
    problems = []

    for f in sorted(reg - voc):
        problems.append(f"'{f}' is in FIELD_REGISTRY but missing from vocabulary.json")

    for f in sorted(voc - reg):
        if vocab[f].get("extractor"):
            problems.append(f"'{f}' lists extractor '{vocab[f]['extractor']}' in vocabulary "
                            f"but is NOT in FIELD_REGISTRY")

    for f in sorted(reg & voc):
        declared = vocab[f].get("extractor")
        actual = short_name(FIELD_REGISTRY[f])
        if declared is None:
            problems.append(f"'{f}' is registered but vocabulary says extractor: null")
        elif declared != actual:
            problems.append(f"'{f}': vocabulary says '{declared}', registry uses '{actual}'")

    if problems:
        print(f"{len(problems)} mismatch(es):")
        for p in problems:
            print("  -", p)
    else:
        print(f"OK: {len(reg)} registered extractors all match vocabulary.json")
    return problems


if __name__ == "__main__":
    check_vocab()