from pathlib import Path
from PIL import Image
from ingestion.cache import get_cache_path

from ingestion.pdf import (
    extract_pdf_text,
    is_scanned_pdf
)

from ingestion.ocr import (
    ocr_pdf,
    ocr_image
)

from ingestion.cleanup import clean_text


def extract_from_document(path):

    path = Path(path)

    suffix = path.suffix.lower()

    cache_file = get_cache_path(path)

    if cache_file.exists():
        return cache_file.read_text(
            encoding="utf-8"
        )

    if suffix == ".pdf":

        if is_scanned_pdf(path):
            text = ocr_pdf(path)
        else:
            text = extract_pdf_text(path)

    else:
        image = Image.open(path)
        text = ocr_image(image)

    text = clean_text(text)

    cache_file.write_text(
        text,
        encoding="utf-8"
    )

    return text