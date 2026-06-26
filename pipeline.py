from utilities import normalize
from registry import FIELD_REGISTRY

def extract_all(text):
    text = normalize(text)

    results = {}

    for field, extractor in FIELD_REGISTRY.items():
        try:
            results[field] = extractor(text)
        except Exception:
            results[field] = None

    return results