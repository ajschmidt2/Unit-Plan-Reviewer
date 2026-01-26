from __future__ import annotations

from typing import List

import fitz
from PIL import Image
import io

ANCHOR_PHRASES = {
    "Floor Plan": ["FLOOR PLAN", "UNIT PLAN"],
    "RCP / Ceiling": ["REFLECTED CEILING", "RCP", "CEILING PLAN"],
    "Interior Elevations": ["INTERIOR ELEVATION", "ELEVATION"],
    "Door Schedule": ["DOOR SCHEDULE"],
}


def _find_anchor_blocks(blocks, phrases: list[str]):
    anchors = []
    for block in blocks:
        x0, y0, x1, y1, text, *_ = block
        if not text:
            continue
        normalized = text.upper()
        for phrase in phrases:
            if phrase in normalized:
                anchors.append({"bbox": (x0, y0, x1, y1), "text": text.strip(), "phrase": phrase})
                break
    return anchors


def _crop_region(image: Image.Image, bbox, scale: float) -> bytes:
    x0, y0, x1, y1 = bbox
    px0 = max(0, int(x0 * scale))
    py0 = max(0, int(y0 * scale))
    px1 = min(image.width, int(x1 * scale))
    py1 = min(image.height, int(y1 * scale))
    cropped = image.crop((px0, py0, px1, py1))
    buf = io.BytesIO()
    cropped.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def extract_regions(
    pdf_bytes: bytes,
    page_index: int,
    dpi: int,
    selected_tags: list[str],
) -> List[dict]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(page_index)
    blocks = page.get_text("blocks")
    page_width = page.rect.width
    page_height = page.rect.height

    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    regions: List[dict] = []
    pad_x = 100
    pad_top = 50
    pad_bottom = 600
    extra_w = 800
    extra_h = 1200

    for tag in selected_tags:
        phrases = ANCHOR_PHRASES.get(tag, [])
        anchors = _find_anchor_blocks(blocks, phrases) if phrases else []

        if anchors:
            for anchor in anchors:
                x0, y0, x1, y1 = anchor["bbox"]
                if tag == "Door Schedule":
                    y1_target = min(page_height, y1 + 1400)
                else:
                    y1_target = min(page_height, y1 + pad_bottom + extra_h)

                crop_bbox = (
                    max(0, x0 - pad_x),
                    max(0, y0 - pad_top),
                    min(page_width, x1 + pad_x + extra_w),
                    y1_target,
                )
                regions.append(
                    {
                        "tag": tag,
                        "bbox": crop_bbox,
                        "png_bytes": _crop_region(image, crop_bbox, zoom),
                        "anchor_text": anchor["text"],
                        "confidence": "High",
                    }
                )
        else:
            crop_bbox = (0, 0, page_width, page_height)
            regions.append(
                {
                    "tag": tag,
                    "bbox": crop_bbox,
                    "png_bytes": _crop_region(image, crop_bbox, zoom),
                    "anchor_text": "",
                    "confidence": "Low",
                }
            )

    return regions
