from dataclasses import dataclass
from typing import List
import fitz
from PIL import Image
import io

@dataclass
class PageImage:
    page_index: int
    png_bytes: bytes
    width: int
    height: int

def pdf_to_page_images(pdf_bytes: bytes, dpi: int = 200) -> List[PageImage]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    for i in range(len(doc)):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        out.append(PageImage(i, buf.getvalue(), pix.width, pix.height))

    return out

def extract_pdf_text(pdf_bytes: bytes, max_pages: int = 30) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts = []
    for i in range(min(len(doc), max_pages)):
        texts.append(doc.load_page(i).get_text("text"))
    return "\n\n---\n\n".join(texts)
