import fitz

def extract_pdf_text(pdf_path):
    doc = fitz.open(pdf_path)
    return "\n".join([page.get_text() for page in doc])


def is_scanned_pdf(pdf_path):
    doc = fitz.open(pdf_path)

    text = ""
    for page in doc:
        text += page.get_text()

    # stronger heuristic
    return len(text.strip()) < 200