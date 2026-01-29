from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import fitz
from PIL import Image, ImageStat, ImageOps, ImageEnhance
import io
import re

@dataclass
class PageImage:
    page_index: int
    png_bytes: bytes
    enhanced_png_bytes: bytes
    width: int
    height: int
    dpi: int

def _to_png_bytes(img: Image.Image, dpi: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, dpi=(dpi, dpi))
    return buf.getvalue()

def _enhance_for_plans(img: Image.Image) -> Image.Image:
    """
    Conservative enhancements: improve legibility without changing geometry.
    Avoid hard thresholding; it can delete light dimension strings.
    """
    x = ImageOps.autocontrast(img, cutoff=1)
    x = ImageEnhance.Sharpness(x).enhance(1.35)
    x = ImageEnhance.Contrast(x).enhance(1.15)
    return x

def pdf_to_page_images(
    pdf_bytes: bytes,
    dpi: int = 450,
    max_pages: Optional[int] = None,
) -> List[PageImage]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out: List[PageImage] = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    page_count = len(doc) if max_pages is None else min(len(doc), max_pages)
    for i in range(page_count):
        page = doc.load_page(i)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        base_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        enhanced_img = _enhance_for_plans(base_img)
        base_png = _to_png_bytes(base_img, dpi=dpi)
        enhanced_png = _to_png_bytes(enhanced_img, dpi=dpi)
        out.append(
            PageImage(
                page_index=i,
                png_bytes=base_png,
                enhanced_png_bytes=enhanced_png,
                width=pix.width,
                height=pix.height,
                dpi=dpi,
            )
        )

    doc.close()
    return out

def extract_pdf_text(pdf_bytes: bytes, max_pages: int = 30) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts = []
    for i in range(min(len(doc), max_pages)):
        texts.append(doc.load_page(i).get_text("text"))
    return "\n\n---\n\n".join(texts)

def extract_page_texts(pdf_bytes: bytes, max_pages: int = 80) -> dict[int, str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = {}
    for i in range(min(len(doc), max_pages)):
        out[i] = doc.load_page(i).get_text("text")
    return out

def extract_sheet_metadata(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    sheet_number = ""
    sheet_title = ""
    number_pattern = re.compile(r"\b[A-Z]{1,4}-?\d{1,4}[A-Z]?\b")
    for idx, line in enumerate(lines):
        if not sheet_number:
            match = number_pattern.search(line)
            if match:
                sheet_number = match.group(0)
                if idx + 1 < len(lines):
                    candidate = lines[idx + 1]
                    if not number_pattern.search(candidate):
                        sheet_title = candidate
        if sheet_title:
            break
    if not sheet_title:
        for line in lines:
            if "PLAN" in line.upper():
                sheet_title = line
                break
    return sheet_number, sheet_title

def extract_title_block_texts(
    pdf_bytes: bytes,
    max_pages: int = 30,
    right_fraction: float = 0.6
) -> List[str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = []
    for i in range(min(len(doc), max_pages)):
        page = doc.load_page(i)
        blocks = page.get_text("blocks")
        width = page.rect.width
        right_edge = width * right_fraction
        pieces = []
        for block in blocks:
            x0, _, _, _, text, *_ = block
            if x0 >= right_edge and text.strip():
                pieces.append(text.strip())
        out.append("\n".join(pieces))
    return out

def detect_page_type(text: str, title_block_text: str) -> str:
    """Auto-detect page type from text content"""
    combined = (text + " " + title_block_text).upper()
    
    if "DOOR SCHEDULE" in combined or "DOOR SCH" in combined:
        return "Door Schedule"
    elif "INTERIOR ELEVATION" in combined or "INT ELEV" in combined or "ELEVATION" in combined:
        return "Interior Elevation"
    elif "REFLECTED CEILING" in combined or "RCP" in combined or "CEILING PLAN" in combined:
        return "Reflected Ceiling Plan"
    elif "FLOOR PLAN" in combined or "UNIT PLAN" in combined or "PLAN" in combined:
        return "Floor Plan"
    else:
        return "Floor Plan"  # Default to floor plan

class ImageQualityChecker:
    """Check if images are suitable for accurate review"""
    
    MIN_WIDTH = 1500  # pixels
    MIN_HEIGHT = 1000  # pixels
    MIN_DPI = 150
    
    @staticmethod
    def _score_png(png_bytes: bytes) -> Dict:
        """Analyze image quality metrics"""
        img = Image.open(io.BytesIO(png_bytes))
        width, height = img.size
        
        # Check DPI if available
        dpi = img.info.get('dpi', (None, None))
        dpi_x, dpi_y = dpi if isinstance(dpi, tuple) else (dpi, dpi)
        
        # Calculate sharpness (std deviation of pixel values)
        stat = ImageStat.Stat(img.convert('L'))
        sharpness = stat.stddev[0]
        
        # Calculate file size
        file_size_kb = len(png_bytes) / 1024
        
        warnings = []
        if width < ImageQualityChecker.MIN_WIDTH or height < ImageQualityChecker.MIN_HEIGHT:
            warnings.append(
                f"Low resolution: {width}x{height}. Recommend at least "
                f"{ImageQualityChecker.MIN_WIDTH}x{ImageQualityChecker.MIN_HEIGHT}"
            )
        
        if dpi_x and dpi_x < ImageQualityChecker.MIN_DPI:
            warnings.append(
                f"Low DPI: {dpi_x}. Recommend at least {ImageQualityChecker.MIN_DPI} DPI"
            )
        
        if sharpness < 30:
            warnings.append(
                f"Low sharpness score: {sharpness:.0f}. Image may be blurry."
            )
        
        quality_score = 100
        if width < ImageQualityChecker.MIN_WIDTH:
            quality_score -= 20
        if dpi_x and dpi_x < ImageQualityChecker.MIN_DPI:
            quality_score -= 20
        if sharpness < 30:
            quality_score -= 30
        
        return {
            "width": width,
            "height": height,
            "dpi": str(dpi_x) if dpi_x else "Unknown",
            "sharpness": round(sharpness, 1),
            "file_size_kb": round(file_size_kb, 1),
            "quality_score": max(0, quality_score),
            "warnings": warnings,
            "suitable_for_review": len(warnings) == 0
        }

    @staticmethod
    def check_image_quality(png_bytes: bytes) -> Dict:
        return ImageQualityChecker._score_png(png_bytes)

    @staticmethod
    def choose_best_for_vision(base_png: bytes, enhanced_png: bytes) -> Tuple[str, Dict]:
        """
        Returns ("base" or "enhanced", metrics_for_winner)
        Prefer higher sharpness, then higher quality_score.
        """
        a = ImageQualityChecker._score_png(base_png)
        b = ImageQualityChecker._score_png(enhanced_png)

        if (b["sharpness"], b["quality_score"]) > (a["sharpness"], a["quality_score"]):
            return "enhanced", b
        return "base", a

def _parse_fraction(s: str) -> float:
    s = s.strip()
    if "/" in s:
        num, den = s.split("/", 1)
        return float(num) / float(den)
    return float(s)

class ScaleVerifier:
    """Verify and parse architectural scale"""
    
    COMMON_SCALES = {
        '1/4" = 1\'-0"': 48,  # 1:48 ratio
        '1/8" = 1\'-0"': 96,
        '3/8" = 1\'-0"': 32,
        '1/2" = 1\'-0"': 24,
        '3/4" = 1\'-0"': 16,
        '1" = 1\'-0"': 12,
        '1 1/2" = 1\'-0"': 8,
    }
    
    @staticmethod
    def parse_scale(scale_str: str) -> Optional[float]:
        """Parse scale string to ratio"""
        scale_str = scale_str.strip()
        
        # Try direct lookup
        if scale_str in ScaleVerifier.COMMON_SCALES:
            return ScaleVerifier.COMMON_SCALES[scale_str]
        
        # Try parsing format like 1/4" = 1'-0"
        match = re.match(r'(\d+(?:\s+\d+/\d+|/\d+)?)"?\s*=\s*(\d+)\'-(\d+)"', scale_str)
        if match:
            inches_on_paper_raw = match.group(1).replace(" ", "")
            inches_on_paper = _parse_fraction(inches_on_paper_raw)
            feet = int(match.group(2))
            inches = int(match.group(3))
            inches_real = feet * 12 + inches
            ratio = inches_real / inches_on_paper
            return ratio
        
        return None
    
    @staticmethod
    def suggest_measurement_extraction(scale_str: str, dpi: int) -> str:
        """Suggest how to extract measurements based on scale"""
        ratio = ScaleVerifier.parse_scale(scale_str)
        
        if not ratio:
            return "Scale format not recognized. Manual measurement verification recommended."
        
        pixels_per_inch_on_paper = dpi
        pixels_per_foot_real = pixels_per_inch_on_paper / ratio * 12
        
        return (
            f"📏 Scale Info:\n"
            f"- Drawing scale: {scale_str} (1:{ratio} ratio)\n"
            f"- At {dpi} DPI: ~{pixels_per_foot_real:.0f} pixels = 1 foot real-world\n"
            f"- For 36\" clearance: expect ~{pixels_per_foot_real * 3:.0f} pixels on drawing\n"
            f"- This information can help verify LLM measurements"
        )

class MeasurementValidator:
    """Validates extracted measurements against code requirements"""
    
    FHA_REQUIREMENTS = {
        "door_clear_opening": (32.0, "inches"),
        "route_width": (36.0, "inches"),
        "bathroom_turning_circle": (60.0, "inches"),
        "kitchen_work_aisle": (40.0, "inches"),
        "maneuvering_clearance_pull_side": (18.0, "inches"),
        "maneuvering_clearance_push_side": (0.0, "inches"),
    }
    
    ANSI_A117_TYPE_A_REQUIREMENTS = {
        "door_clear_opening": (32.0, "inches"),
        "route_width": (36.0, "inches"),
        "bathroom_turning_circle": (60.0, "inches"),
        "kitchen_work_aisle": (40.0, "inches"),
        "toilet_centerline_to_wall": (18.0, "inches"),
        "toilet_clearance_depth": (56.0, "inches"),
    }
    
    def __init__(self, ruleset: str):
        self.ruleset = ruleset
        if "TYPE_A" in ruleset:
            self.requirements = self.ANSI_A117_TYPE_A_REQUIREMENTS
        else:
            self.requirements = self.FHA_REQUIREMENTS
    
    def parse_dimension(self, dim_str: str) -> Optional[float]:
        """Parse dimension string like '2'-10\"' or '32\"' to inches"""
        # Handle feet and inches: 2'-10"
        feet_inches = re.match(r"(\d+)'-(\d+)\"", dim_str)
        if feet_inches:
            feet, inches = feet_inches.groups()
            return int(feet) * 12 + int(inches)
        
        # Handle just inches: 32"
        inches_only = re.match(r"(\d+(?:\.\d+)?)\"", dim_str)
        if inches_only:
            return float(inches_only.group(1))
        
        # Handle decimal feet: 2.833'
        feet_only = re.match(r"(\d+(?:\.\d+)?)'", dim_str)
        if feet_only:
            return float(feet_only.group(1)) * 12
        
        return None
    
    def validate_measurement(self, element_type: str, measured_value: float) -> Dict:
        """Check if a measurement meets code requirements"""
        if element_type not in self.requirements:
            return {"compliant": None, "message": "Unknown element type"}
        
        required_value, unit = self.requirements[element_type]
        
        compliant = measured_value >= required_value
        difference = measured_value - required_value
        
        return {
            "compliant": compliant,
            "measured": measured_value,
            "required": required_value,
            "difference": difference,
            "unit": unit,
            "message": f"{'✓' if compliant else '✗'} {measured_value}{unit} (required: {required_value}{unit})"
        }
