import io

import fitz                 # PyMuPDF
import cv2
import numpy as np
from PIL import Image
import pytesseract

# --- Windows: if Tesseract isn't on your PATH, point pytesseract at the binary.
# Install the UB Mannheim build first: https://github.com/UB-Mannheim/tesseract/wiki
# then uncomment and adjust this to your install path:
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\dyqi1\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
#C:\Users\dyqi1\AppData\Local\Programs\Tesseract-OCR

# Tesseract page-segmentation mode. 3 = fully automatic (good default for letters);
# try 6 ("assume a single uniform block") if a page is one column of text.
TESS_CONFIG = "--psm 3"


def _preprocess(image: Image.Image) -> Image.Image:
    """Any PIL image -> binarized grayscale, which Tesseract reads most reliably."""
    arr = np.array(image)
    if arr.ndim == 3:
        code = cv2.COLOR_RGB2GRAY if arr.shape[2] == 3 else cv2.COLOR_RGBA2GRAY
        arr = cv2.cvtColor(arr, code)
    arr = cv2.adaptiveThreshold(
        arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2
    )
    return Image.fromarray(arr)


def ocr_image(image) -> str:
    if not isinstance(image, Image.Image):
        image = Image.fromarray(np.asarray(image))
    processed = _preprocess(image)
    return pytesseract.image_to_string(processed, config=TESS_CONFIG)


def ocr_pdf(pdf_path) -> str:
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        # 3x render is a good speed/quality balance; bump to Matrix(4,4) only if small text is being missed.
        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        pages.append(ocr_image(image))
    return "\n\n".join(pages)