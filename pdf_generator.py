"""
Enhanced PDF Generator - Creates Professional TDS using IKIO Template
Generates structured, color-coded Technical Data Sheets matching IKIO demo format
"""
import io
import fitz  # PyMuPDF for template handling
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, KeepTogether, Flowable, HRFlowable,
    ListFlowable, ListItem
)
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Rect, Line
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage

from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import asdict
from datetime import datetime
import os
import sys
import subprocess
import re
from xml.sax.saxutils import escape

from config import COMPANY_CONFIG, PDF_SETTINGS, ASSETS_DIR, OUTPUT_DIR
from data_mapper import IKIOTDSData, TDSSpecificationTable, TDSAccessory

try:
    from image_asset_manager import get_asset_manager
except ImportError:
    get_asset_manager = None


def _limit_words(text: str, max_words: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    words = cleaned.split()
    if len(words) <= max_words:
        return cleaned
    return " ".join(words[:max_words]).rstrip(",;:-") + "..."


# Template PDF path (header/footer template used for all TDS generations)
TEMPLATE_PDF_PATH = Path(__file__).parent / "Ikio_Header_Footer_Formate.pdf"


# IKIO Brand Colors - matching the demo PDF exactly
class BrandColors:
    # Primary Colors
    DARK_BLUE = colors.HexColor("#3fad42")      # IKIO green
    NAVY = colors.HexColor("#3fad42")
    
    # Section Header - Dark blue with subtle styling
    SECTION_HEADER_BG = colors.HexColor("#3fad42")  # IKIO green for section headers
    SECTION_HEADER_TEXT = colors.white
    
    # Table Colors
    TABLE_HEADER_BG = colors.HexColor("#3fad42")   # IKIO green header
    TABLE_HEADER_TEXT = colors.white
    TABLE_ROW_LIGHT = colors.HexColor("#ffffff")   # White
    TABLE_ROW_ALT = colors.HexColor("#f2f7f1")     # Very light green-gray
    TABLE_BORDER = colors.HexColor("#dee2e6")      # Light gray border
    TABLE_TEXT = colors.HexColor("#212529")        # Dark text
    
    # Text Colors
    TEXT_BLACK = colors.HexColor("#212529")
    TEXT_DARK = colors.HexColor("#495057")
    TEXT_MEDIUM = colors.HexColor("#6c757d")
    TEXT_LIGHT = colors.HexColor("#adb5bd")
    
    # Accent Colors
    ACCENT_GREEN = colors.HexColor("#3fad42")      # IKIO green accent
    ACCENT_BLUE = colors.HexColor("#3fad42")
    ACCENT_RED = colors.HexColor("#3fad42")
    
    # Label Background (light blue-gray for spec labels)
    LABEL_BG = colors.HexColor("#e9f3e8")
    
    # Background
    WHITE = colors.white
    LIGHT_BG = colors.HexColor("#f8f9fa")


class SectionHeader(Flowable):
    """Creates a professional dark blue section header bar"""
    
    def __init__(self, text, width, height=20, bg_color=None, text_color=None):
        Flowable.__init__(self)
        self.text = text
        self.width = width
        self.height = height
        self.bg_color = bg_color or BrandColors.SECTION_HEADER_BG
        self.text_color = text_color or BrandColors.SECTION_HEADER_TEXT

    def draw(self):
        self.canv.saveState()
        
        # Draw background rectangle
        self.canv.setFillColor(self.bg_color)
        self.canv.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        
        # Draw text - bold white, centered vertically
        self.canv.setFillColor(self.text_color)
        self.canv.setFont("Helvetica-Bold", 9)
        self.canv.drawString(8, 6, self.text.upper())
        
        self.canv.restoreState()
    
    def wrap(self, availWidth, availHeight):
        return self.width, self.height


class IKIOTDSGenerator:
    """
    Generates Professional Technical Data Sheets using IKIO Template
    Matches the demo PDF format with proper structure and styling
    """
    
    def __init__(self, output_path: str = None, template_path: str = None):
        # Template path
        self.output_path = output_path
        self.template_path = template_path or str(TEMPLATE_PDF_PATH)

        # Default page size (A4) - will be overridden by template if available
        self.page_width, self.page_height = A4

        tpl_size = self._get_template_page_size(self.template_path)
        if tpl_size:
            self.page_width, self.page_height = tpl_size
        
        # Margins - leave space for template header/footer
        self.margin_left = 15 * mm
        self.margin_right = 15 * mm
        self.margin_top = 32 * mm      # Space for header
        self.margin_bottom = 22 * mm   # Space for footer
        self.content_width = self.page_width - self.margin_left - self.margin_right
        
        self.styles = self._setup_styles()
        self.tds_data: Optional[IKIOTDSData] = None

    def _get_template_page_size(self, template_path: str) -> Optional[Tuple[float, float]]:
        """Return template (width, height) so content aligns to the fixed spec sheet."""
        try:
            path_obj = Path(template_path)
            if not path_obj.exists():
                return None
            doc = fitz.open(str(path_obj))
            rect = doc[0].rect
            size = (rect.width, rect.height)
            doc.close()
            return size
        except Exception as e:
            print(f"Warning: Could not read template size ({e})")
            return None

    def _open_pdf(self, pdf_path: str) -> None:
        """Open the generated PDF in the system's default PDF editor/viewer."""
        if not os.path.exists(pdf_path):
            return
        try:
            if os.name == "nt":
                os.startfile(pdf_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", pdf_path])
            else:
                subprocess.Popen(["xdg-open", pdf_path])
        except Exception as e:
            print(f"Warning: Could not auto-open PDF ({e})")

    def _find_spec_value(self, tds_data: IKIOTDSData, labels: List[str]) -> str:
        """Find a spec value by label from spec tables or direct fields."""
        label_set = {l.strip().lower() for l in labels}

        # Search spec tables first (preserves vendor-specific values)
        for table in tds_data.spec_tables:
            for row in table.rows:
                if not row or len(row) < 2:
                    continue
                row_label = str(row[0]).strip().lower()
                if row_label in label_set:
                    values = [str(v).strip() for v in row[1:] if str(v).strip() and str(v).strip().lower() not in ['', 'n/a', 'na', '-']]
                    if not values:
                        continue
                    if len(values) == 1:
                        return values[0]
                    return " / ".join(values)
                
                # Try partial match
                for label in labels:
                    if label.lower() in row_label or row_label in label.lower():
                        values = [str(v).strip() for v in row[1:] if str(v).strip() and str(v).strip().lower() not in ['', 'n/a', 'na', '-']]
                        if values:
                            return values[0] if len(values) == 1 else " / ".join(values)

        # Fallback to direct fields
        for label in labels:
            attr = label.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")
            if hasattr(tds_data, attr):
                value = getattr(tds_data, attr) or ""
                if value and str(value).strip() and str(value).strip().lower() not in ['n/a', 'na', '-']:
                    return str(value).strip()

        return ""

    def _format_inline(self, label: str, value: str) -> str:
        if not value:
            return ""
        return f"{label} {value}".strip()

    def _get_layout_rect(self, tds_data: IKIOTDSData, block_id: str, fallback: fitz.Rect) -> fitz.Rect:
        """Resolve an optional user-edited layout block into a PDF rect."""
        try:
            layout = getattr(tds_data, "layout_overrides", {}) or {}
            blocks = layout.get("blocks", {}) or {}
            block = blocks.get(block_id)
            if not isinstance(block, dict):
                return fallback
            x = float(block.get("x", fallback.x0))
            y = float(block.get("y", fallback.y0))
            width = max(20.0, float(block.get("width", fallback.width)))
            height = max(12.0, float(block.get("height", fallback.height)))
            return fitz.Rect(x, y, x + width, y + height)
        except Exception:
            return fallback

    def _get_page_layout_rect(self, tds_data: IKIOTDSData, page_key: str, block_id: str, fallback: fitz.Rect) -> fitz.Rect:
        """Resolve page-specific visual editor blocks for follow-up pages."""
        try:
            layout = getattr(tds_data, "layout_overrides", {}) or {}
            pages = layout.get("pages", {}) or {}
            page_blocks = pages.get(page_key, {}) or {}
            block = page_blocks.get(block_id)
            if not isinstance(block, dict):
                return fallback
            x = float(block.get("x", fallback.x0))
            y = float(block.get("y", fallback.y0))
            width = max(20.0, float(block.get("width", fallback.width)))
            height = max(12.0, float(block.get("height", fallback.height)))
            return fitz.Rect(x, y, x + width, y + height)
        except Exception:
            return fallback

    def _get_warranty_badge(self, tds_data: IKIOTDSData) -> Optional[bytes]:
        """Resolve the standard warranty badge from the current warranty term."""
        if not get_asset_manager:
            return None
        try:
            warranty_value = str(getattr(tds_data, "warranty_years", "") or getattr(tds_data, "warranty", "")).strip()
            match = re.search(r"(\d+)", warranty_value)
            years = int(match.group(1)) if match else None
            return get_asset_manager().get_warranty_image(years)
        except Exception:
            return None

    def _build_template_header_fields(self, tds_data: IKIOTDSData) -> Dict[str, str]:
        """Return values stamped into the shared page header."""
        project_name = str(tds_data.project_name or "").strip()
        catalog_number = str(
            tds_data.catalog_number or tds_data.item_sku or tds_data.model_number or ""
        ).strip()
        fixture_schedule = str(tds_data.fixture_schedule or "").strip()
        note = str(
            tds_data.product_title or tds_data.product_category or tds_data.product_name or ""
        ).strip()
        return {
            "project_name": project_name,
            "catalog_number": catalog_number,
            "fixture_schedule": fixture_schedule,
            "note": note,
        }

    def _section_label(self, tds_data: IKIOTDSData, key: str, fallback: str) -> str:
        """Resolve editable section labels from the form."""
        labels = getattr(tds_data, "section_headings", {}) or {}
        value = labels.get(key)
        return str(value).strip() if str(value or "").strip() else fallback

    def _stamp_template_header_footer(
        self,
        page: fitz.Page,
        tds_data: IKIOTDSData,
        page_num: int,
    ) -> None:
        """Stamp dynamic values into the shared A4 header/footer template."""
        fields = self._build_template_header_fields(tds_data)
        text_dark = (40 / 255, 40 / 255, 40 / 255)
        white = (1, 1, 1)

        # Clear and restamp footer page number in the new template format.
        page_no_rect = fitz.Rect(520.0, 797.0, 572.5, 809.5)
        page.draw_rect(page_no_rect, color=white, fill=white, overlay=True)
        page.insert_textbox(
            page_no_rect,
            f"Page No : {page_num:02d}",
            fontsize=6.2,
            fontname="helv",
            color=text_dark,
            align=2,
        )

        field_rects = {
            "project_name": fitz.Rect(188.0, 36.0, 277.0, 47.0),
            "catalog_number": fitz.Rect(307.0, 36.0, 386.0, 47.0),
            "note": fitz.Rect(180.0, 50.0, 275.0, 62.0),
            "fixture_schedule": fitz.Rect(344.0, 50.0, 488.0, 62.0),
        }

        for field_name, rect in field_rects.items():
            value = fields.get(field_name, "")
            if not value:
                continue
            page.insert_textbox(
                rect,
                value,
                fontsize=6.8,
                fontname="helv",
                color=text_dark,
                align=0,
            )

    def _get_overview_rows(self, tds_data: IKIOTDSData) -> List[Tuple[str, str]]:
        """Resolve the high-priority overview spec rows shown on page 1."""
        custom_rows = getattr(tds_data, "overview_rows", None) or []
        if custom_rows:
            return [
                (str(row[0]).strip(), str(row[1]).strip())
                for row in custom_rows
                if len(row) >= 2 and str(row[0]).strip() and str(row[1]).strip()
            ]

        mounting_value = (
            tds_data.mounting_type
            or self._find_spec_value(tds_data, ["Mounting Options", "Mounting Option", "Mounting Type", "Mounting"])
        )
        if not mounting_value and getattr(tds_data, "mounting_options", None):
            mounting_names = [str(item.name).strip() for item in tds_data.mounting_options if str(getattr(item, "name", "")).strip()]
            if mounting_names:
                mounting_value = " | ".join(mounting_names[:3])

        overview_pairs = [
            ("Power", self._find_spec_value(tds_data, ["Power", "Wattage"]) or (tds_data.wattage or "")),
            ("Input Voltage", self._find_spec_value(tds_data, ["Voltage", "Input Voltage"]) or (tds_data.input_voltage or "")),
            ("Power Factor", tds_data.power_factor or self._find_spec_value(tds_data, ["Power Factor"])),
            ("Surge Protection", tds_data.surge_protection or self._find_spec_value(tds_data, ["Surge Protection", "Surge"])),
            ("Driver Type", tds_data.power_supply or self._find_spec_value(tds_data, ["Driver Type", "Driver", "Power Supply"])),
            ("Control", tds_data.dimming or self._find_spec_value(tds_data, ["Control", "Dimming", "Dimmable Light Control"])),
            ("LED Type", tds_data.led_light_source or self._find_spec_value(tds_data, ["LED Type", "LED Light Source", "Source"])),
            ("Luminous Flux (±10%)", tds_data.lumens or self._find_spec_value(tds_data, ["Lumens", "Luminous Flux"])),
            ("Efficacy", tds_data.efficacy or self._find_spec_value(tds_data, ["Efficacy"])),
            ("Correlated Color Temperature", tds_data.cct or self._find_spec_value(tds_data, ["Color Temperature (CCT)", "CCT"])),
            ("Temperature", tds_data.operating_temp or self._find_spec_value(tds_data, ["Operating Temperature", "Operating Temp", "Ambient"])),
            ("Color Rendering Index", tds_data.cri or self._find_spec_value(tds_data, ["Color Rendering Index (CRI)", "CRI"])),
            ("Beam Angle", tds_data.beam_angle or self._find_spec_value(tds_data, ["Beam Angle"])),
            ("Mounting Option", mounting_value),
            ("Material", tds_data.housing_material or self._find_spec_value(tds_data, ["Housing", "Material"])),
            ("Lens", tds_data.lens_material or self._find_spec_value(tds_data, ["Lens", "Cover Material", "Lens Material"])),
            ("Finish", tds_data.finish or self._find_spec_value(tds_data, ["Finish"])),
            ("Fixture Color", self._find_spec_value(tds_data, ["Fixture Color", "Color"]) or tds_data.finish),
            ("EPA", tds_data.epa or self._find_spec_value(tds_data, ["Effective Projected Area (EPA)", "EPA"])),
            ("IK Rating", tds_data.ik_rating or self._find_spec_value(tds_data, ["Impact Protection Rating (IK)", "IK"])),
            ("IP Rating", tds_data.ip_rating or self._find_spec_value(tds_data, ["Ingress Protection Rating (IP)", "IP"])),
            ("Category of Corrosion", self._find_spec_value(tds_data, ["Category of Corrosion", "Corrosion"])),
            ("Warranty", tds_data.warranty_years or tds_data.warranty or self._find_spec_value(tds_data, ["Warranty", "Warranty (Years)"])),
        ]
        return [(label, str(value).strip()) for label, value in overview_pairs if str(value or "").strip()]

    def _draw_badges_row(self, page: fitz.Page, badges: List[bytes], rect: fitz.Rect, max_badges: int = 4) -> None:
        """Render a centered horizontal row of certification badges."""
        if not badges:
            return
        usable = [badge for badge in badges[:max_badges] if badge]
        if not usable:
            return
        gap = 10
        badge_w = min(rect.height, max(36, (rect.width - gap * (len(usable) - 1)) / max(len(usable), 1)))
        total_w = badge_w * len(usable) + gap * (len(usable) - 1)
        x = rect.x0 + max(0, (rect.width - total_w) / 2)
        y = rect.y0 + max(0, (rect.height - badge_w) / 2)
        for badge in usable:
            badge_rect = fitz.Rect(x, y, x + badge_w, y + badge_w)
            try:
                page.insert_image(badge_rect, stream=badge, keep_proportion=True, overlay=True)
            except Exception as e:
                print(f"Warning: could not place certification badge ({e})")
            x += badge_w + gap

    def _draw_overview_table(self, page: fitz.Page, rect: fitz.Rect, rows: List[Tuple[str, str]], title: str = "OVERVIEW") -> None:
        """Draw the page-1 overview table using the demo-style ruled layout."""
        if not rows:
            return
        text_dark = (0.15, 0.15, 0.15)
        line_color = (0.72, 0.72, 0.72)
        header_color = (0.05, 0.05, 0.05)
        label_x = rect.x0 + 4
        value_x = rect.x0 + rect.width * 0.46
        visible_rows = rows[:23]
        row_h = min(22, max(17, (rect.height - 24) / max(len(visible_rows), 1)))
        label_font = 7.1 if row_h >= 20 else 6.5
        value_font = 6.7 if row_h >= 20 else 6.1

        page.insert_text(
            fitz.Point(rect.x0, rect.y0 + 11),
            title,
            fontsize=10,
            fontname="helv",
            color=header_color,
        )
        y = rect.y0 + 22
        for label, value in visible_rows:
            if y + row_h > rect.y1:
                break
            page.draw_line(
                fitz.Point(rect.x0, y),
                fitz.Point(rect.x1, y),
                color=line_color,
                width=0.7,
            )
            page.insert_textbox(
                fitz.Rect(label_x, y + 4, value_x - 6, y + row_h - 2),
                label,
                fontsize=label_font,
                fontname="helv",
                color=text_dark,
                align=0,
            )
            page.insert_textbox(
                fitz.Rect(value_x, y + 4, rect.x1 - 3, y + row_h - 2),
                value,
                fontsize=value_font,
                fontname="helv",
                color=text_dark,
                align=0,
            )
            y += row_h
        page.draw_line(fitz.Point(rect.x0, y), fitz.Point(rect.x1, y), color=line_color, width=0.7)

    def _render_template_page1(self, page: fitz.Page, tds_data: IKIOTDSData) -> None:
        """
        Draws page-1 content directly onto the template so fields align with
        the provided header/footer and section headings.
        Coordinates were measured from the template (612 x 792 pts).
        """
        brand_green = (63 / 255, 173 / 255, 66 / 255)
        text_dark = (40 / 255, 40 / 255, 40 / 255)
        line_color = (0.72, 0.72, 0.72)
        muted_text = (0.25, 0.25, 0.25)

        product_name_box = self._get_layout_rect(tds_data, "product_name", fitz.Rect(20, 68, 294, 102))
        product_title_box = self._get_layout_rect(tds_data, "product_title", fitz.Rect(20, 94, 294, 136))
        image_box = self._get_layout_rect(tds_data, "product_image", fitz.Rect(44, 138, 282, 454))
        overview_table_box = self._get_layout_rect(tds_data, "overview", fitz.Rect(308, 66, 570, 566))
        badges_box = self._get_layout_rect(tds_data, "qualifications", fitz.Rect(22, 482, 280, 546))
        description_box = self._get_layout_rect(tds_data, "product_description", fitz.Rect(20, 558, 272, 644))
        features_box = self._get_layout_rect(tds_data, "features", fitz.Rect(20, 655, 294, 739))
        application_box = self._get_layout_rect(tds_data, "application_area", fitz.Rect(308, 558, 570, 604))
        warranty_block = self._get_layout_rect(tds_data, "warranty", fitz.Rect(308, 620, 570, 740))
        warranty_label_box = fitz.Rect(
            warranty_block.x0,
            warranty_block.y0,
            warranty_block.x1,
            min(warranty_block.y0 + 14, warranty_block.y1),
        )
        warranty_rule_y = min(warranty_block.y0 + 18, warranty_block.y1)
        warranty_badge_size = max(42, min(64, warranty_block.width * 0.28))
        warranty_icon_left = warranty_block.x0 + (warranty_block.width - warranty_badge_size) / 2
        warranty_icon_box = fitz.Rect(
            warranty_icon_left,
            min(warranty_block.y0 + 28, warranty_block.y1),
            warranty_icon_left + warranty_badge_size,
            min(warranty_block.y0 + 28 + warranty_badge_size, warranty_block.y1 - 8),
        )
        warranty_box = fitz.Rect(
            warranty_block.x0,
            min(warranty_icon_box.y1 + 8, warranty_block.y1),
            warranty_block.x1,
            warranty_block.y1,
        )

        def write(rect: fitz.Rect, text: str, size: float = 9, color=text_dark, font="helv", align=0):
            """Write text to a rect with automatic overflow handling"""
            if not text:
                return
            
            text = str(text).strip()
            if not text:
                return
            
            # Try to fit text in the box
            # First attempt: use specified font size
            result = page.insert_textbox(rect, text, fontsize=size, fontname=font, color=color, align=align)
            
            # If text doesn't fit (result < 0 means overflow), try smaller font
            if result < 0 and size > 6:
                # Reduce font size progressively
                for reduced_size in [size * 0.9, size * 0.8, size * 0.7, 6]:
                    result = page.insert_textbox(rect, text, fontsize=reduced_size, fontname=font, color=color, align=align)
                    if result >= 0:
                        break
            
            # If still doesn't fit, truncate with ellipsis
            if result < 0:
                max_chars = int(len(text) * 0.7)
                truncated = text[:max_chars] + "..."
                page.insert_textbox(rect, truncated, fontsize=6, fontname=font, color=color, align=align)

        # ---- Dynamic content ----
        self._stamp_template_header_footer(page, tds_data, page_num=1)
        title = str(tds_data.product_name or "").strip()
        subtitle = str(tds_data.product_title or "").strip()
        category = str(tds_data.category_path or tds_data.product_category or "").strip()
        category = category.upper()
        if subtitle and subtitle.strip().lower() == category.strip().lower():
            category = ""

        write(product_name_box, title, size=22, color=(0, 0, 0))
        if subtitle:
            subtitle_box = fitz.Rect(
                product_title_box.x0,
                product_title_box.y0,
                product_title_box.x1,
                min(product_title_box.y0 + max(12, product_title_box.height / 2), product_title_box.y1),
            )
            write(subtitle_box, subtitle, size=9, color=muted_text, font="helv")
        if category:
            category_box = fitz.Rect(
                product_title_box.x0,
                min(product_title_box.y0 + max(12, product_title_box.height / 2), product_title_box.y1),
                product_title_box.x1,
                product_title_box.y1,
            )
            write(category_box, category, size=9, color=muted_text, font="helv")
        title_rule_y = min(max(product_name_box.y1, product_title_box.y1) + 6, page.rect.height - 1)
        page.draw_line(
            fitz.Point(product_name_box.x0, title_rule_y),
            fitz.Point(max(product_name_box.x1, product_title_box.x1), title_rule_y),
            color=line_color,
            width=0.8,
        )

        badges = getattr(tds_data, "certification_badges", None) or []
        self._draw_badges_row(page, badges, badges_box)

        overview_rows = self._get_overview_rows(tds_data)
        self._draw_overview_table(
            page,
            overview_table_box,
            overview_rows,
            self._section_label(tds_data, "overview", "OVERVIEW")
        )

        write(
            fitz.Rect(description_box.x0, description_box.y0, description_box.x1, description_box.y0 + 14),
            self._section_label(tds_data, "product_description", "Product Description"),
            size=10,
            color=(0, 0, 0),
        )
        page.draw_line(
            fitz.Point(description_box.x0, description_box.y0 + 18),
            fitz.Point(description_box.x1, description_box.y0 + 18),
            color=line_color,
            width=0.8,
        )
        write(
            fitz.Rect(description_box.x0, description_box.y0 + 25, description_box.x1, description_box.y1),
            tds_data.product_description or "",
            size=7.1,
            color=text_dark,
            font="helv",
        )

        write(
            fitz.Rect(features_box.x0, features_box.y0, features_box.x1, features_box.y0 + 14),
            self._section_label(tds_data, "features", "Features"),
            size=10,
            color=(0, 0, 0),
        )
        page.draw_line(
            fitz.Point(features_box.x0, features_box.y0 + 18),
            fitz.Point(features_box.x1, features_box.y0 + 18),
            color=line_color,
            width=0.8,
        )
        features = [str(f).strip() for f in (tds_data.features or []) if str(f).strip()]
        feature_text = "\n".join(f"- {feature}" for feature in features[:5])
        write(fitz.Rect(features_box.x0, features_box.y0 + 25, features_box.x1, features_box.y1), feature_text, size=7.0, color=text_dark, font="helv")

        application_text = ", ".join(str(item).strip() for item in (tds_data.applications or []) if str(item).strip())
        write(
            fitz.Rect(application_box.x0, application_box.y0, application_box.x1, application_box.y0 + 14),
            self._section_label(tds_data, "application_area", "Application Area"),
            size=10,
            color=(0, 0, 0),
        )
        page.draw_line(
            fitz.Point(application_box.x0, application_box.y0 + 18),
            fitz.Point(application_box.x1, application_box.y0 + 18),
            color=line_color,
            width=0.8,
        )
        write(fitz.Rect(application_box.x0, application_box.y0 + 25, application_box.x1, application_box.y1), application_text, size=7.0, color=text_dark, font="helv")

        write(warranty_label_box, self._section_label(tds_data, "warranty", "Warranty"), size=10, color=(0, 0, 0))
        page.draw_line(
            fitz.Point(warranty_block.x0, warranty_rule_y),
            fitz.Point(warranty_block.x1, warranty_rule_y),
            color=line_color,
            width=0.8,
        )

        warranty_text = tds_data.warranty_limitation or ""
        if warranty_text:
            write(
                warranty_box,
                f"Warranty Limitations: {warranty_text}",
                size=5.6,
                color=text_dark,
                font="helv",
                align=0
            )
        warranty_badge = self._get_warranty_badge(tds_data)
        if warranty_badge:
            try:
                page.insert_image(warranty_icon_box, stream=warranty_badge, keep_proportion=True, overlay=True)
            except Exception:
                pass

        # Optional image placement
        placed_image = False
        if getattr(tds_data, "product_images", None):
            try:
                img_bytes = tds_data.product_images[0]
                if img_bytes:
                    page.insert_image(image_box, stream=img_bytes, keep_proportion=True, overlay=True)
                    placed_image = True
            except Exception as e:
                print(f"Warning: could not place product image on page 1 ({e})")

        if not placed_image and getattr(tds_data, "extracted_images", None):
            try:
                first_img = tds_data.extracted_images[0]
                img_path = first_img.get("path") or first_img.get("file_path")
                img_bytes = first_img.get("image_data")
                if img_bytes:
                    page.insert_image(image_box, stream=img_bytes, keep_proportion=True, overlay=True)
                elif img_path and Path(img_path).exists():
                    page.insert_image(image_box, filename=img_path, keep_proportion=True, overlay=True)
            except Exception as e:
                print(f"Warning: could not place image on page 1 ({e})")



    def _setup_styles(self) -> Dict[str, ParagraphStyle]:
        """Setup paragraph styles matching IKIO demo format"""
        styles = getSampleStyleSheet()
        
        custom_styles = {
            # Part Number / Model at top
            'PartNumber': ParagraphStyle(
                'PartNumber',
                fontName='Helvetica-Bold',
                fontSize=14,
                textColor=BrandColors.DARK_BLUE,
                spaceAfter=2,
                spaceBefore=0,
                alignment=TA_LEFT,
                leading=18
            ),
            
            # Product Title - Below part number
            'ProductTitle': ParagraphStyle(
                'ProductTitle',
                fontName='Helvetica',
                fontSize=11,
                textColor=BrandColors.TEXT_DARK,
                spaceAfter=8,
                spaceBefore=0,
                alignment=TA_LEFT,
                leading=14
            ),
            
            # Section Title (for text-only section titles)
            'SectionTitle': ParagraphStyle(
                'SectionTitle',
                fontName='Helvetica-Bold',
                fontSize=9,
                textColor=BrandColors.SECTION_HEADER_TEXT,
                spaceBefore=0,
                spaceAfter=0,
                alignment=TA_LEFT
            ),

            'SectionTitlePlain': ParagraphStyle(
                'SectionTitlePlain',
                fontName='Helvetica-Bold',
                fontSize=11,
                textColor=BrandColors.TEXT_BLACK,
                spaceBefore=0,
                spaceAfter=0,
                alignment=TA_LEFT,
                leading=13
            ),
            
            # Body Text
            'BodyText': ParagraphStyle(
                'BodyText',
                fontName='Helvetica',
                fontSize=8,
                textColor=BrandColors.TEXT_DARK,
                spaceAfter=4,
                alignment=TA_LEFT,
                leading=11
            ),
            
            # Body Text Justified (for descriptions)
            'BodyTextJustified': ParagraphStyle(
                'BodyTextJustified',
                fontName='Helvetica',
                fontSize=8,
                textColor=BrandColors.TEXT_DARK,
                spaceAfter=6,
                alignment=TA_JUSTIFY,
                leading=11
            ),

            'PageIdentity': ParagraphStyle(
                'PageIdentity',
                fontName='Helvetica',
                fontSize=9,
                textColor=BrandColors.TEXT_DARK,
                spaceBefore=0,
                spaceAfter=0,
                alignment=TA_LEFT,
                leading=11
            ),
            
            # Table Header Text
            'TableHeader': ParagraphStyle(
                'TableHeader',
                fontName='Helvetica-Bold',
                fontSize=7,
                textColor=BrandColors.TABLE_HEADER_TEXT,
                alignment=TA_CENTER,
                leading=9
            ),
            
            # Table Cell Text - Left aligned
            'TableCell': ParagraphStyle(
                'TableCell',
                fontName='Helvetica',
                fontSize=7,
                textColor=BrandColors.TABLE_TEXT,
                alignment=TA_LEFT,
                leading=9
            ),
            
            # Table Cell Text - Center aligned
            'TableCellCenter': ParagraphStyle(
                'TableCellCenter',
                fontName='Helvetica',
                fontSize=7,
                textColor=BrandColors.TABLE_TEXT,
                alignment=TA_CENTER,
                leading=9
            ),
            
            # Overview Label (left column in overview table)
            'OverviewLabel': ParagraphStyle(
                'OverviewLabel',
                fontName='Helvetica',
                fontSize=7,
                textColor=BrandColors.TEXT_MEDIUM,
                alignment=TA_LEFT,
                leading=9
            ),
            
            # Overview Value (right column in overview table)
            'OverviewValue': ParagraphStyle(
                'OverviewValue',
                fontName='Helvetica-Bold',
                fontSize=7,
                textColor=BrandColors.TEXT_BLACK,
                alignment=TA_LEFT,
                leading=9
            ),
            
            # Spec Label (left column in 2-col tables)
            'SpecLabel': ParagraphStyle(
                'SpecLabel',
                fontName='Helvetica',
                fontSize=7,
                textColor=BrandColors.TEXT_MEDIUM,
                alignment=TA_LEFT,
                leading=9
            ),
            
            # Spec Value (right column in 2-col tables)
            'SpecValue': ParagraphStyle(
                'SpecValue',
                fontName='Helvetica-Bold',
                fontSize=7,
                textColor=BrandColors.TEXT_BLACK,
                alignment=TA_LEFT,
                leading=9
            ),
            
            # Bullet Text / Features
            'BulletText': ParagraphStyle(
                'BulletText',
                fontName='Helvetica',
                fontSize=7.5,
                textColor=BrandColors.TEXT_DARK,
                leftIndent=8,
                spaceAfter=2,
                leading=10
            ),
            
            # Small Text (for notes, disclaimers)
            'SmallText': ParagraphStyle(
                'SmallText',
                fontName='Helvetica',
                fontSize=6,
                textColor=BrandColors.TEXT_MEDIUM,
                spaceAfter=2,
                alignment=TA_LEFT,
                leading=8
            ),
            
            # Warranty Text
            'WarrantyText': ParagraphStyle(
                'WarrantyText',
                fontName='Helvetica',
                fontSize=6.5,
                textColor=BrandColors.TEXT_DARK,
                spaceAfter=2,
                alignment=TA_JUSTIFY,
                leading=8
            ),
        }
        
        return custom_styles

    def _create_section_header(self, title: str) -> SectionHeader:
        """Create a dark blue section header bar"""
        return SectionHeader(title.upper(), self.content_width)

    def _build_page1_header(self, tds_data: IKIOTDSData) -> List[Any]:
        """Build the top header with part number, title and product image"""
        elements = []
        
        # Get part number or model
        part_number = tds_data.model_number or ""
        product_title = f"{tds_data.product_name}"
        if tds_data.product_category:
            product_title = f"{tds_data.product_category} | {tds_data.product_name}"
        
        # Find main product image
        main_image = None
        for img in tds_data.extracted_images:
            if img.get("image_type") == "product" and img.get("image_data"):
                main_image = img
                break
        if not main_image:
            for img in tds_data.extracted_images:
                if img.get("image_data") and img.get("width", 0) >= 100:
                    main_image = img
                    break
        
        # Create left side (text) and right side (image) layout
        left_content = []
        
        # Part Number (large, dark blue)
        left_content.append(Paragraph(part_number, self.styles['PartNumber']))
        
        # Product Title (smaller, gray)
        left_content.append(Paragraph(product_title, self.styles['ProductTitle']))
        
        # Build table layout
        if main_image:
            try:
                img_bytes = main_image["image_data"]
                pil_img = PILImage.open(io.BytesIO(img_bytes))
                orig_width, orig_height = pil_img.size
                
                max_width = 120
                max_height = 90
                scale = min(max_width / orig_width, max_height / orig_height, 1)
                new_width = orig_width * scale
                new_height = orig_height * scale
                
                img_io = io.BytesIO(img_bytes)
                rl_image = Image(img_io, width=new_width, height=new_height)
                
                # Create 2-column layout: text left, image right
                header_table = Table(
                    [[left_content, rl_image]],
                    colWidths=[self.content_width * 0.65, self.content_width * 0.35]
                )
                header_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ]))
                elements.append(header_table)
            except Exception as e:
                print(f"Warning: Could not render product image: {e}")
                for item in left_content:
                    elements.append(item)
        else:
            for item in left_content:
                elements.append(item)
        
        elements.append(Spacer(1, 8))
        return elements

    def _build_description_section(self, tds_data: IKIOTDSData) -> List[Any]:
        """Build product description section"""
        elements = []
        
        if not tds_data.product_description:
            return elements
        
        elements.append(self._create_section_header("Product Description"))
        elements.append(Spacer(1, 4))
        
        elements.append(Paragraph(
            tds_data.product_description,
            self.styles['BodyTextJustified']
        ))
        
        elements.append(Spacer(1, 6))
        return elements

    def _build_features_section(self, features: List[str]) -> List[Any]:
        """Build features section with bullet points"""
        elements = []
        
        if not features:
            return elements
        
        elements.append(self._create_section_header("Features"))
        elements.append(Spacer(1, 4))
        
        for feature in features[:10]:  # Limit to 10 features
            bullet_text = f"- {feature}"
            elements.append(Paragraph(bullet_text, self.styles['BulletText']))
        
        elements.append(Spacer(1, 6))
        return elements

    def _build_overview_section(self, tds_data: IKIOTDSData) -> List[Any]:
        """Build the OVERVIEW section - key specs in a structured grid"""
        elements = []
        
        # Collect ALL overview specs in order
        specs = []
        
        # Row 1: Power, Voltage, LED Module (if applicable)
        if tds_data.wattage:
            specs.append(("Power", tds_data.wattage))
        if tds_data.input_voltage:
            specs.append(("Voltage", tds_data.input_voltage))
        if tds_data.lumens:
            specs.append(("Lumens", tds_data.lumens))
        if tds_data.efficacy:
            specs.append(("Efficacy", tds_data.efficacy))
        
        # Row 2: CCT, CRI, Beam Angle
        if tds_data.cct:
            specs.append(("Color Temperature (CCT)", tds_data.cct))
        if tds_data.cri:
            specs.append(("CRI", tds_data.cri))
        if tds_data.beam_angle:
            specs.append(("Beam Angle", tds_data.beam_angle))
        
        # Row 3: IP Rating, IK Rating
        if tds_data.ip_rating:
            specs.append(("Ingress Protection Rating (IP)", tds_data.ip_rating))
        if tds_data.ik_rating:
            specs.append(("IK Rating", tds_data.ik_rating))
        
        # Row 4: Materials
        if tds_data.lens_material:
            specs.append(("Lens", tds_data.lens_material))
        if tds_data.housing_material:
            specs.append(("Housing", tds_data.housing_material))
        
        # Row 5: Dimensions
        if tds_data.dimensions:
            specs.append(("Dimensions", tds_data.dimensions))
        if tds_data.product_weight:
            specs.append(("Net Weight", tds_data.product_weight))
        if tds_data.cutout_size:
            specs.append(("Cutout Size", tds_data.cutout_size))
        
        # Row 6: Other
        if tds_data.dimming:
            specs.append(("Dimming", tds_data.dimming))
        if tds_data.lifespan:
            specs.append(("Average Life", tds_data.lifespan))
        if tds_data.operating_temp:
            specs.append(("Operating Temperature", tds_data.operating_temp))
        if tds_data.mounting_type:
            specs.append(("Mounting", tds_data.mounting_type))
        
        # Packaging
        if tds_data.packaging_dimensions:
            specs.append(("Box Dimensions", tds_data.packaging_dimensions))
        if tds_data.box_weight:
            specs.append(("Box Weight", tds_data.box_weight))
        
        if not specs:
            return elements
        
        elements.append(self._create_section_header("Overview"))
        elements.append(Spacer(1, 4))
        
        # Create a 4-column grid table (2 pairs of label-value)
        table_data = []
        for i in range(0, len(specs), 2):
            row = []
            
            # First pair
            label1, value1 = specs[i]
            row.append(Paragraph(label1, self.styles['OverviewLabel']))
            row.append(Paragraph(str(value1), self.styles['OverviewValue']))
            
            # Second pair (if exists)
            if i + 1 < len(specs):
                label2, value2 = specs[i + 1]
                row.append(Paragraph(label2, self.styles['OverviewLabel']))
                row.append(Paragraph(str(value2), self.styles['OverviewValue']))
            else:
                row.extend(["", ""])
            
            table_data.append(row)
        
        # Column widths
        col_widths = [
            self.content_width * 0.28,
            self.content_width * 0.22,
            self.content_width * 0.28,
            self.content_width * 0.22
        ]
        
        table = Table(table_data, colWidths=col_widths)
        
        # Style with alternating rows
        style_commands = [
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, BrandColors.TABLE_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]
        
        # Alternating row colors
        for i in range(len(table_data)):
            if i % 2 == 0:
                style_commands.append(('BACKGROUND', (0, i), (-1, i), BrandColors.TABLE_ROW_ALT))
            else:
                style_commands.append(('BACKGROUND', (0, i), (-1, i), BrandColors.TABLE_ROW_LIGHT))
        
        table.setStyle(TableStyle(style_commands))
        elements.append(table)
        elements.append(Spacer(1, 6))
        
        return elements

    def _build_applications_section(self, applications: List[str]) -> List[Any]:
        """Build application areas section"""
        elements = []
        
        if not applications:
            return elements
        
        elements.append(self._create_section_header("Application Area"))
        elements.append(Spacer(1, 4))
        
        # Join applications with commas for compact display
        app_text = ", ".join(applications)
        elements.append(Paragraph(app_text, self.styles['BodyText']))
        
        elements.append(Spacer(1, 6))
        return elements

    def _build_warranty_section(self, tds_data: IKIOTDSData) -> List[Any]:
        """Build warranty section with limitation text"""
        elements = []
        
        # Section header with warranty period
        warranty_period = tds_data.warranty or "5 Years"
        elements.append(self._create_section_header(f"Warranty"))
        elements.append(Spacer(1, 4))
        
        # Warranty limitation text
        warranty_text = """Warranty Limitations: To ensure eligibility, the product must be installed by a certified electrician in accordance with the guidelines outlined in the installation sheet. The warranty remains valid only if all operating conditions strictly adhere to the parameters specified in the installation sheet. Any installation errors or deviations from the provided instructions will void warranty coverage. Additional coverage options may be available for purchase--please contact IKIO representatives for more information. Warranty claims must be initiated by submitting a completed RMA form. For full warranty details and terms, refer to the comprehensive warranty document."""
        
        # Check if there are custom warranty notes
        for note in (tds_data.notes or []):
            if 'warranty' in note.lower() or 'limitation' in note.lower():
                warranty_text = note
                break
        
        elements.append(Paragraph(warranty_text, self.styles['WarrantyText']))
        elements.append(Spacer(1, 6))
        
        return elements

    def _build_product_specs_grid(self, tds_data: IKIOTDSData) -> List[Any]:
        """Build two-column product specifications grid for page 2."""
        elements = []

        pairs = [
            ("Power Factor", tds_data.power_factor),
            ("THD", tds_data.thd),
            ("Beam Angle", tds_data.beam_angle),
            ("Dimmable Lighting Control", tds_data.dimming),
            ("Operating Temperature", tds_data.operating_temp),
            ("Suitable Location", tds_data.suitable_location),
            ("IP", tds_data.ip_rating),
            ("IK", tds_data.ik_rating),
            ("Average Life (Hours)", tds_data.lifespan),
            ("Warranty (Years)", tds_data.warranty_years or tds_data.warranty),
            ("LED Light Source", tds_data.led_light_source),
            ("Housing", tds_data.housing_material),
            ("Cover Material / Lens", tds_data.lens_material),
            ("Diffuser", tds_data.diffuser),
            ("Base / Power Supply", tds_data.power_supply),
            ("Finish", tds_data.finish),
        ]

        rows = []
        for i in range(0, len(pairs), 2):
            left = pairs[i]
            right = pairs[i + 1] if i + 1 < len(pairs) else ("", "")
            rows.append([
                Paragraph(f"<b>{left[0]}</b>", self.styles['TableCell']),
                Paragraph(left[1] or "", self.styles['TableCell']),
                Paragraph(f"<b>{right[0]}</b>", self.styles['TableCell']),
                Paragraph(right[1] or "", self.styles['TableCell']),
            ])

        if not rows:
            return elements

        table = Table(
            rows,
            colWidths=[
                self.content_width * 0.18,
                self.content_width * 0.32,
                self.content_width * 0.18,
                self.content_width * 0.32,
            ]
        )
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, BrandColors.TABLE_BORDER),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (0, -1), BrandColors.LABEL_BG),
            ('BACKGROUND', (2, 0), (2, -1), BrandColors.LABEL_BG),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
        ]))
        section_title = self._section_label(tds_data, "product_specifications", "Product Specifications")
        elements.append(Paragraph(f"<b>{section_title}</b>", self.styles['SectionTitlePlain']))
        elements.append(Spacer(1, 3))
        elements.append(HRFlowable(width="100%", thickness=0.7, color=BrandColors.TABLE_BORDER))
        elements.append(Spacer(1, 6))
        elements.append(table)
        elements.append(Spacer(1, 8))
        return elements

    def _build_photometrics_section(self, tds_data: IKIOTDSData) -> List[Any]:
        """Build photometrics section with note and diagram."""
        elements = []
        note = tds_data.photometrics_note or ""
        diagram_data = tds_data.photometrics_diagram_data

        if not note and not diagram_data:
            return elements

        elements.append(self._create_section_header(self._section_label(tds_data, "photometrics", "Photometrics")))
        elements.append(Spacer(1, 4))

        if note:
            elements.append(Paragraph(note, self.styles['BodyText']))
            elements.append(Spacer(1, 4))

        if diagram_data:
            try:
                pil_img = PILImage.open(io.BytesIO(diagram_data))
                orig_width, orig_height = pil_img.size
                max_width = self.content_width * 0.7
                max_height = 180
                scale = min(max_width / orig_width, max_height / orig_height, 1)
                new_width = orig_width * scale
                new_height = orig_height * scale
                img_io = io.BytesIO(diagram_data)
                rl_image = Image(img_io, width=new_width, height=new_height)
                img_table = Table([[rl_image]], colWidths=[self.content_width])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                elements.append(img_table)
                elements.append(Spacer(1, 6))
            except Exception as e:
                print(f"Warning: Could not render photometrics diagram: {e}")

        return elements

    def _build_spec_table_section(self, spec_table: TDSSpecificationTable, title_override: str = None) -> List[Any]:
        """Build a specification table with IKIO styling"""
        elements = []
        
        if not spec_table.rows:
            return elements
        
        # Section header
        title = title_override or spec_table.title or "Product Specifications"
        if self._is_product_spec_matrix(spec_table):
            return self._build_product_spec_matrix_section(spec_table, title)

        elements.append(Paragraph(f"<b>{title}</b>", self.styles['SectionTitlePlain']))
        elements.append(Spacer(1, 3))
        elements.append(HRFlowable(width="100%", thickness=0.7, color=BrandColors.TABLE_BORDER))
        elements.append(Spacer(1, 6))

        collapsed_rows = self._collapse_continuation_rows(spec_table.rows)
        
        # Create table data
        table_data = []
        
        # Add headers if present
        if spec_table.headers:
            header_row = [
                Paragraph(f"<b>{h}</b>", self.styles['TableHeader']) 
                for h in spec_table.headers
            ]
            table_data.append(header_row)
        
        # Add data rows
        for row in collapsed_rows:
            table_row = [
                self._render_table_cell(cell, self.styles['TableCellCenter'])
                for cell in row
            ]
            table_data.append(table_row)
        
        # Calculate column widths evenly
        num_cols = len(spec_table.headers) if spec_table.headers else len(collapsed_rows[0]) if collapsed_rows else 1
        col_width = self.content_width / num_cols
        col_widths = [col_width] * num_cols
        
        table = Table(table_data, colWidths=col_widths)
        
        # Apply styling
        style_commands = [
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 6.2),
            # Header row - dark blue background
            ('BACKGROUND', (0, 0), (-1, 0), BrandColors.TABLE_HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), BrandColors.TABLE_HEADER_TEXT),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, BrandColors.TABLE_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]
        
        # Alternating row colors for data rows
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                style_commands.append(('BACKGROUND', (0, i), (-1, i), BrandColors.TABLE_ROW_ALT))
            else:
                style_commands.append(('BACKGROUND', (0, i), (-1, i), BrandColors.TABLE_ROW_LIGHT))
        
        table.setStyle(TableStyle(style_commands))
        elements.append(table)
        elements.append(Spacer(1, 8))
        
        return elements

    def _render_table_cell(self, value: Any, style: ParagraphStyle) -> Paragraph:
        text = str(value or "")
        return Paragraph(escape(text).replace("\n", "<br/>"), style)

    def _collapse_continuation_rows(self, rows: List[List[Any]]) -> List[List[str]]:
        collapsed: List[List[str]] = []
        for raw_row in rows or []:
            row = [str(cell or "").strip() for cell in raw_row]
            if not any(row):
                continue
            if collapsed and row and not row[0]:
                previous = collapsed[-1]
                width = max(len(previous), len(row))
                previous.extend([""] * (width - len(previous)))
                row.extend([""] * (width - len(row)))
                for index, cell in enumerate(row):
                    if not cell:
                        continue
                    previous[index] = f"{previous[index]}\n{cell}".strip() if previous[index] else cell
                continue
            collapsed.append(row)
        return collapsed

    def _is_product_spec_matrix(self, spec_table: TDSSpecificationTable) -> bool:
        headers = [re.sub(r"\s+", " ", str(header or "")).strip().lower() for header in (spec_table.headers or [])]
        if len(headers) < 8:
            return False

        expected_tokens = {
            "part number",
            "power",
            "voltage",
            "lumen",
            "efficacy",
            "cri",
            "current",
            "cct",
            "thd",
            "distribution",
        }
        header_blob = " | ".join(headers)
        token_hits = sum(1 for token in expected_tokens if token in header_blob)
        return token_hits >= 8

    def _build_product_spec_matrix_section(self, spec_table: TDSSpecificationTable, title: str) -> List[Any]:
        elements = [
            Paragraph(f"<b>{title}</b>", self.styles['SectionTitlePlain']),
            Spacer(1, 3),
            HRFlowable(width="100%", thickness=0.7, color=BrandColors.TABLE_BORDER),
            Spacer(1, 6),
        ]

        unit_map = {
            "Power Selectable": "W",
            "Voltage": "V",
            "Lumen Output": "lm",
            "Efficacy": "lm/W",
            "Current": "A",
            "CCT Selectable": "K",
        }
        col_widths = [
            self.content_width * 0.25,
            self.content_width * 0.08,
            self.content_width * 0.09,
            self.content_width * 0.10,
            self.content_width * 0.08,
            self.content_width * 0.05,
            self.content_width * 0.06,
            self.content_width * 0.12,
            self.content_width * 0.05,
            self.content_width * 0.12,
        ]

        normalized_rows = [
            [str(cell or "").strip() for cell in row[: len(spec_table.headers)]]
            for row in spec_table.rows
            if any(str(cell or "").strip() for cell in row)
        ]

        grouped_rows: List[List[str]] = []
        index = 0
        while index < len(normalized_rows):
            part_number = normalized_rows[index][0] if normalized_rows[index] else ""
            end_index = index + 1
            while end_index < len(normalized_rows):
                next_part_number = normalized_rows[end_index][0] if normalized_rows[end_index] else ""
                if next_part_number and next_part_number != part_number:
                    break
                end_index += 1
            group = [list(normalized_rows[row_index]) for row_index in range(index, end_index)]
            collapsed_group = []
            for column_index in range(len(spec_table.headers)):
                values: List[str] = []
                for row in group:
                    value = row[column_index].strip()
                    if value and value not in values:
                        values.append(value)
                collapsed_group.append("\n".join(values))
            grouped_rows.append(collapsed_group)
            index = end_index

        header_cells = []
        for header in spec_table.headers:
            unit = unit_map.get(str(header), "")
            if unit:
                header_cells.append(
                    Paragraph(f"<b>{header}</b><br/><font size='5'>{unit}</font>", self.styles['TableHeader'])
                )
            else:
                label = str(header).replace(" ", "<br/>") if header == "Light Distribution" else str(header)
                header_cells.append(Paragraph(f"<b>{label}</b>", self.styles['TableHeader']))
        table_data = [header_cells]

        for row in grouped_rows:
            rendered_row = []
            for cell_index, cell in enumerate(row):
                style = self.styles['TableCell'] if cell_index == 0 else self.styles['TableCellCenter']
                rendered_row.append(self._render_table_cell(cell, style))
            table_data.append(rendered_row)

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        style_commands = [
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), BrandColors.TABLE_HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), BrandColors.TABLE_HEADER_TEXT),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('TOPPADDING', (0, 0), (-1, 0), 3),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 3),
            ('TOPPADDING', (0, 1), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('BACKGROUND', (0, 1), (-1, -1), BrandColors.TABLE_ROW_LIGHT),
        ]
        for row_number in range(1, len(table_data)):
            if row_number % 2 == 0:
                style_commands.append(('BACKGROUND', (0, row_number), (-1, row_number), BrandColors.TABLE_ROW_ALT))

        table.setStyle(TableStyle(style_commands))
        elements.append(table)
        elements.append(Spacer(1, 8))
        return elements

    def _build_ordering_info_table(self, tds_data: IKIOTDSData) -> List[Any]:
        """Build the part number breakdown / ordering information table"""
        elements = []
        title = self._section_label(tds_data, "product_ordering_information", "Product Ordering Information")
        ordering_info = tds_data.ordering_info
        ordering_structure = getattr(tds_data, "ordering_structure", None)
        if not ordering_info and not tds_data.spec_tables:
            return elements
        if (not ordering_info) and ordering_structure and getattr(ordering_structure, "components", None):
            return self._build_ordering_structure_matrix(title, ordering_structure)
        
        # If we have ordering_info list with dicts
        if ordering_info and isinstance(ordering_info, list) and len(ordering_info) > 0:
            if isinstance(ordering_info[0], dict):
                header_order = []
                for item in ordering_info:
                    for key, value in item.items():
                        if str(value or "").strip() and key not in header_order:
                            header_order.append(str(key))

                if header_order:
                    elements.append(Paragraph(f"<b>{title}</b>", self.styles['SectionTitlePlain']))
                    elements.append(Spacer(1, 3))
                    elements.append(HRFlowable(width="100%", thickness=0.7, color=BrandColors.TABLE_BORDER))
                    elements.append(Spacer(1, 6))

                    table_data = [[Paragraph(f"<b>{h}</b>", self.styles['TableHeader']) for h in header_order]]
                    for item in ordering_info:
                        row = [
                            Paragraph(str(item.get(header, "")), self.styles['TableCellCenter'])
                            for header in header_order
                        ]
                        table_data.append(row)

                    col_width = self.content_width / max(1, len(header_order))
                    table = Table(table_data, colWidths=[col_width] * len(header_order))
                    style_commands = [
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('BACKGROUND', (0, 0), (-1, 0), BrandColors.TABLE_HEADER_BG),
                        ('TEXTCOLOR', (0, 0), (-1, 0), BrandColors.TABLE_HEADER_TEXT),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('GRID', (0, 0), (-1, -1), 0.5, BrandColors.TABLE_BORDER),
                        ('TOPPADDING', (0, 0), (-1, -1), 3),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                    ]
                    for i in range(1, len(table_data)):
                        if i % 2 == 0:
                            style_commands.append(('BACKGROUND', (0, i), (-1, i), BrandColors.TABLE_ROW_ALT))
                    table.setStyle(TableStyle(style_commands))
                    elements.append(table)
                    elements.append(Spacer(1, 8))

        elif ordering_info and isinstance(ordering_info, dict):
            headers = [str(h) for h in ordering_info.get("headers", []) if str(h).strip()]
            subheaders = [str(h or "").strip() for h in ordering_info.get("subheaders", [])]
            groups = ordering_info.get("groups", []) or []
            rows = ordering_info.get("rows", [])
            if headers and rows:
                if groups or subheaders:
                    elements.extend(self._build_grouped_ordering_table(title, headers, rows, groups, subheaders, ordering_structure))
                elif len(headers) >= 8:
                    elements.extend(self._build_wide_ordering_table(title, headers, rows, ordering_structure))
                else:
                    table = TDSSpecificationTable(
                        title=title,
                        headers=headers,
                        rows=rows
                    )
                    elements.extend(self._build_spec_table_section(
                        table,
                        title_override=title
                    ))
        
        return elements

    def _build_grouped_ordering_table(
        self,
        title: str,
        headers: List[str],
        rows: List[List[Any]],
        groups: List[Dict[str, Any]],
        subheaders: List[str],
        ordering_structure: Any = None,
    ) -> List[Any]:
        elements: List[Any] = [
            Paragraph(f"<b>{title}</b>", self.styles['SectionTitlePlain']),
            Spacer(1, 3),
        ]

        example_part_number = ""
        if ordering_structure is not None:
            example_part_number = str(getattr(ordering_structure, "example_part_number", "") or "").strip()
        if example_part_number:
            elements.append(Paragraph(f"<b>Typical order example:</b> {example_part_number}", self.styles['SmallText']))
            elements.append(Spacer(1, 4))

        safe_headers = [str(header or "").strip() for header in headers]
        safe_rows = [[str(cell or "").strip() for cell in row[: len(safe_headers)]] for row in rows if any(str(cell or "").strip() for cell in row)]
        if not safe_headers or not safe_rows:
            return elements

        normalized_subheaders = (subheaders + [""] * len(safe_headers))[: len(safe_headers)] if subheaders else [""] * len(safe_headers)
        normalized_groups = []
        remaining = len(safe_headers)
        for group in groups or []:
            if remaining <= 0:
                break
            span = max(1, min(int(group.get("span", 1) or 1), remaining))
            normalized_groups.append({"label": str(group.get("label", "") or "").strip(), "span": span})
            remaining -= span
        if remaining > 0:
            normalized_groups.append({"label": "", "span": remaining})

        table_data: List[List[Any]] = []
        if normalized_groups:
            group_row = []
            for group in normalized_groups:
                label = escape(group["label"]).replace("\n", "<br/>")
                group_row.append(Paragraph(f"<b>{label}</b>" if label else "", self.styles['TableHeader']))
            table_data.append(group_row)

        table_data.append([Paragraph(f"<b>{escape(header)}</b>", self.styles['TableHeader']) for header in safe_headers])
        if any(normalized_subheaders):
            table_data.append([
                Paragraph(f"<b>{escape(subheader)}</b>" if subheader else "", self.styles['TableCellCenter'])
                for subheader in normalized_subheaders
            ])

        collapsed_rows = self._collapse_continuation_rows(safe_rows)
        for row in collapsed_rows:
            padded = (row + [""] * len(safe_headers))[: len(safe_headers)]
            rendered = []
            for index, cell in enumerate(padded):
                style = self.styles['TableCell'] if index < 2 else self.styles['TableCellCenter']
                rendered.append(self._render_table_cell(cell, style))
            table_data.append(rendered)

        weights = []
        for index, header in enumerate(safe_headers):
            normalized = re.sub(r"\s+", " ", header.lower()).strip()
            weight = 1.0
            if index < 2:
                weight = 1.5
            elif any(keyword in normalized for keyword in ("manufacturer", "distribution", "finish", "diffuser", "sensor")):
                weight = 1.25
            weights.append(weight)
        total_weight = sum(weights) or len(weights)
        col_widths = [self.content_width * (weight / total_weight) for weight in weights]

        table = Table(table_data, colWidths=col_widths)
        style_commands = [
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.4, BrandColors.TABLE_BORDER),
            ('BACKGROUND', (0, 0), (-1, 0), BrandColors.TABLE_HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), BrandColors.TABLE_HEADER_TEXT),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ]

        header_row_index = 1 if normalized_groups else 0
        style_commands.extend([
            ('BACKGROUND', (0, header_row_index), (-1, header_row_index), colors.HexColor("#DADADA")),
            ('TEXTCOLOR', (0, header_row_index), (-1, header_row_index), colors.black),
            ('FONTNAME', (0, header_row_index), (-1, header_row_index), 'Helvetica-Bold'),
        ])
        if any(normalized_subheaders):
            subheader_row_index = header_row_index + 1
            style_commands.extend([
                ('BACKGROUND', (0, subheader_row_index), (-1, subheader_row_index), BrandColors.TABLE_ROW_ALT),
                ('FONTNAME', (0, subheader_row_index), (-1, subheader_row_index), 'Helvetica-Bold'),
            ])
        first_data_row = header_row_index + (2 if any(normalized_subheaders) else 1)
        for row_number in range(first_data_row, len(table_data)):
            bg = BrandColors.TABLE_ROW_ALT if (row_number - first_data_row) % 2 else BrandColors.TABLE_ROW_LIGHT
            style_commands.append(('BACKGROUND', (0, row_number), (-1, row_number), bg))

        if normalized_groups:
            cursor = 0
            for group in normalized_groups:
                span = group["span"]
                if span > 1:
                    style_commands.append(('SPAN', (cursor, 0), (cursor + span - 1, 0)))
                cursor += span

        merge_columns = min(2, len(safe_headers))
        for col in range(merge_columns):
            row_index = first_data_row
            while row_index < len(table_data):
                cell_text = collapsed_rows[row_index - first_data_row][col] if row_index - first_data_row < len(collapsed_rows) and col < len(collapsed_rows[row_index - first_data_row]) else ""
                if not cell_text:
                    row_index += 1
                    continue
                next_index = row_index + 1
                while next_index < len(table_data):
                    compare_text = collapsed_rows[next_index - first_data_row][col] if next_index - first_data_row < len(collapsed_rows) and col < len(collapsed_rows[next_index - first_data_row]) else ""
                    if compare_text:
                        break
                    next_index += 1
                if next_index - row_index > 1:
                    style_commands.append(('SPAN', (col, row_index), (col, next_index - 1)))
                    style_commands.append(('VALIGN', (col, row_index), (col, next_index - 1), 'TOP'))
                row_index = next_index

        elements.append(HRFlowable(width="100%", thickness=0.7, color=BrandColors.TABLE_BORDER))
        elements.append(Spacer(1, 6))
        table.setStyle(TableStyle(style_commands))
        elements.append(table)
        elements.append(Spacer(1, 8))
        return elements

    def _build_ordering_structure_matrix(self, title: str, ordering_structure: Any) -> List[Any]:
        elements = [
            Paragraph(f"<b>{title}</b>", self.styles['SectionTitlePlain']),
            Spacer(1, 3),
        ]

        example_part_number = str(getattr(ordering_structure, "example_part_number", "") or "").strip()
        if example_part_number:
            elements.append(Paragraph(f"<b>Typical order example:</b> {example_part_number}", self.styles['SmallText']))
            elements.append(Spacer(1, 4))

        components = getattr(ordering_structure, "components", []) or []
        if not components:
            return elements

        headers = [str(component.get("name", "") or component.get("code", "")).strip() for component in components]
        code_row = [str(component.get("code", "")).strip() for component in components]
        max_options = max((len(component.get("options", []) or []) for component in components), default=0)
        rows: List[List[str]] = [code_row]

        for option_index in range(max_options):
            row = []
            for component in components:
                options = component.get("options", []) or []
                if option_index < len(options):
                    option = options[option_index] or {}
                    option_code = str(option.get("code", "")).strip()
                    option_desc = str(option.get("description", "")).strip()
                    row.append("\n".join(part for part in [option_code, option_desc] if part))
                else:
                    row.append("")
            rows.append(row)

        elements.extend(self._build_wide_ordering_table(title, headers, rows, ordering_structure, include_title=False))
        return elements

    def _build_wide_ordering_table(self, title: str, headers: List[str], rows: List[List[Any]], ordering_structure: Any = None, include_title: bool = True) -> List[Any]:
        elements: List[Any] = []
        if include_title:
            elements.extend([
                Paragraph(f"<b>{title}</b>", self.styles['SectionTitlePlain']),
                Spacer(1, 3),
            ])
            example_part_number = ""
            if ordering_structure is not None:
                example_part_number = str(getattr(ordering_structure, "example_part_number", "") or "").strip()
            if example_part_number:
                elements.append(Paragraph(f"<b>Typical order example:</b> {example_part_number}", self.styles['SmallText']))
                elements.append(Spacer(1, 4))

        safe_headers = [str(header or "").strip() for header in headers]
        safe_rows = [[str(cell or "").strip() for cell in row[: len(safe_headers)]] for row in rows if any(str(cell or "").strip() for cell in row)]
        if not safe_headers or not safe_rows:
            return elements

        table_data = [
            [Paragraph(f"<b>{header}</b>", self.styles['TableHeader']) for header in safe_headers]
        ]
        for row in safe_rows:
            table_data.append([Paragraph(cell.replace("\n", "<br/>"), self.styles['TableCell']) for cell in row])

        weights = []
        for header in safe_headers:
            normalized = re.sub(r"\s+", " ", header.lower()).strip()
            weight = 1.0
            if any(keyword in normalized for keyword in ("family", "electrical", "construction", "mounting", "manufacturer", "finish")):
                weight = 1.4
            elif len(normalized) > 12:
                weight = 1.25
            weights.append(weight)
        total_weight = sum(weights) or len(weights)
        col_widths = [self.content_width * (weight / total_weight) for weight in weights]

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        style_commands = [
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BACKGROUND', (0, 0), (-1, 0), BrandColors.TABLE_HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), BrandColors.TABLE_HEADER_TEXT),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
            ('FONTSIZE', (0, 0), (-1, 0), 5.3),
            ('FONTSIZE', (0, 1), (-1, -1), 4.5),
            ('TOPPADDING', (0, 0), (-1, 0), 2),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
            ('TOPPADDING', (0, 1), (-1, -1), 1.5),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 1.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('BACKGROUND', (0, 1), (-1, -1), BrandColors.TABLE_ROW_LIGHT),
        ]
        for row_number in range(2, len(table_data), 2):
            style_commands.append(('BACKGROUND', (0, row_number), (-1, row_number), BrandColors.TABLE_ROW_ALT))
        table.setStyle(TableStyle(style_commands))
        elements.append(HRFlowable(width="100%", thickness=0.7, color=BrandColors.TABLE_BORDER))
        elements.append(Spacer(1, 6))
        elements.append(table)
        elements.append(Spacer(1, 8))
        return elements

    def _build_secondary_page_intro(self, tds_data: IKIOTDSData) -> List[Any]:
        """Build the demo-style product identity row used on content pages."""
        title_parts = [part.strip() for part in [tds_data.product_name, tds_data.product_title, tds_data.product_category] if str(part or "").strip()]
        title = " | ".join(title_parts)
        badges = getattr(tds_data, "certification_badges", None) or []

        left = Paragraph(title, self.styles['PageIdentity'])
        badge_cells: List[Any] = []
        for badge in badges[:4]:
            try:
                img = Image(io.BytesIO(badge), width=20, height=20)
                badge_cells.append(img)
            except Exception:
                continue
        if not badge_cells:
            badge_cells = [Paragraph("", self.styles['BodyText'])]

        badge_table = Table([badge_cells], colWidths=[20] * len(badge_cells))
        badge_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        intro = Table([[left, badge_table]], colWidths=[self.content_width * 0.76, self.content_width * 0.24])
        intro.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        return [
            intro,
            Spacer(1, 4),
            HRFlowable(width="100%", thickness=0.7, color=colors.black),
            Spacer(1, 8),
        ]

    def _build_dimensions_section(self, tds_data: IKIOTDSData) -> List[Any]:
        """Build dimensions section with diagram and tables"""
        elements = []

        has_dims = any([
            tds_data.product_length, tds_data.product_width, tds_data.product_height,
            tds_data.wire_length, tds_data.net_weight,
            tds_data.slip_fitter_length, tds_data.slip_fitter_width, tds_data.slip_fitter_height,
            tds_data.slip_fitter_weight
        ])

        dim_images = [img for img in tds_data.extracted_images
                     if img.get("image_type") == "dimension" and img.get("image_data")]
        diagram_data = tds_data.dimension_diagram_data
        if not diagram_data and dim_images:
            diagram_data = dim_images[0]["image_data"]

        if not has_dims and not diagram_data:
            return elements

        elements.append(self._create_section_header("Dimensions"))
        elements.append(Spacer(1, 4))

        def build_dim_table(title: str, rows: List[Tuple[str, str]]):
            table_data = [[Paragraph(f"<b>{title}</b>", self.styles['TableHeader']), ""]]
            for label, value in rows:
                table_data.append([
                    Paragraph(label, self.styles['TableCell']),
                    Paragraph(value or "", self.styles['TableCell'])
                ])
            table = Table(table_data, colWidths=[self.content_width * 0.24, self.content_width * 0.26])
            table.setStyle(TableStyle([
                ('SPAN', (0, 0), (1, 0)),
                ('BACKGROUND', (0, 0), (1, 0), BrandColors.TABLE_HEADER_BG),
                ('TEXTCOLOR', (0, 0), (1, 0), BrandColors.TABLE_HEADER_TEXT),
                ('GRID', (0, 0), (-1, -1), 0.5, BrandColors.TABLE_BORDER),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            return table

        # Filter out empty values and "Not specified" text
        def clean_value(val):
            if not val:
                return ""
            val_str = str(val).strip()
            if val_str.lower() in ["not specified", "n/a", "na", "-", "none", ""]:
                return ""
            return val_str
        
        product_rows = [
            ("Length (L)", clean_value(tds_data.product_length)),
            ("Width (W)", clean_value(tds_data.product_width)),
            ("Height (H)", clean_value(tds_data.product_height)),
            ("Wire Length", clean_value(tds_data.wire_length)),
            ("Net Weight", clean_value(tds_data.net_weight)),
        ]
        slip_rows = [
            ("Length (L)", clean_value(tds_data.slip_fitter_length)),
            ("Width (W)", clean_value(tds_data.slip_fitter_width)),
            ("Height (H)", clean_value(tds_data.slip_fitter_height)),
            ("Net Weight", clean_value(tds_data.slip_fitter_weight)),
        ]
        
        # Only show rows that have values
        product_rows = [(label, val) for label, val in product_rows if val]
        slip_rows = [(label, val) for label, val in slip_rows if val]

        product_table = build_dim_table("Product Dimensions & Weight", product_rows)
        slip_table = build_dim_table("Slip Fitter Dimensions & Weight", slip_rows)

        combined = Table([[product_table, slip_table]], colWidths=[self.content_width * 0.5, self.content_width * 0.5])
        combined.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(combined)
        elements.append(Spacer(1, 6))

        if diagram_data:
            try:
                pil_img = PILImage.open(io.BytesIO(diagram_data))
                orig_width, orig_height = pil_img.size
                max_width = self.content_width * 0.85
                max_height = 200
                scale = min(max_width / orig_width, max_height / orig_height, 1)
                new_width = orig_width * scale
                new_height = orig_height * scale
                img_io = io.BytesIO(diagram_data)
                rl_image = Image(img_io, width=new_width, height=new_height)
                img_table = Table([[rl_image]], colWidths=[self.content_width])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                elements.append(img_table)
                elements.append(Spacer(1, 8))
            except Exception as e:
                print(f"Warning: Could not render dimension diagram: {e}")

        return elements

    def _build_epa_section(self, tds_data: IKIOTDSData) -> List[Any]:
        """Build EPA specifications table."""
        if not tds_data.epa_table or not tds_data.epa_table.rows:
            return []
        return self._build_spec_table_section(tds_data.epa_table, title_override="EPA Specifications")

    def _build_distributions_section(self, tds_data: IKIOTDSData) -> List[Any]:
        """Build light distribution / IES diagrams section"""
        elements = []
        
        # Find distribution/photometric images
        dist_images = []
        for img in tds_data.extracted_images:
            img_type = img.get("image_type", "")
            if ("distribution" in img_type.lower() or 
                "photometric" in img_type.lower() or
                "ies" in img_type.lower() or
                "polar" in img_type.lower()) and img.get("image_data"):
                dist_images.append(img)
        
        # Also add beam angle diagrams
        for diagram in tds_data.beam_angle_diagrams:
            if diagram.get("image_data"):
                dist_images.append({
                    "image_data": diagram["image_data"],
                    "image_type": "distribution",
                    "description": diagram.get("type", "Beam Pattern")
                })
        
        if not dist_images:
            return elements
        
        elements.append(self._create_section_header("Distributions"))
        elements.append(Spacer(1, 4))
        
        for img_data in dist_images[:4]:  # Limit to 4
            try:
                img_bytes = img_data["image_data"]
                pil_img = PILImage.open(io.BytesIO(img_bytes))
                orig_width, orig_height = pil_img.size
                
                max_width = self.content_width * 0.5
                max_height = 150
                
                scale = min(max_width / orig_width, max_height / orig_height, 1)
                new_width = orig_width * scale
                new_height = orig_height * scale
                
                img_io = io.BytesIO(img_bytes)
                rl_image = Image(img_io, width=new_width, height=new_height)
                
                img_table = Table([[rl_image]], colWidths=[self.content_width])
                img_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ]))
                elements.append(img_table)
                elements.append(Spacer(1, 4))
                
            except Exception as e:
                print(f"Warning: Could not render distribution image: {e}")
        
        elements.append(Spacer(1, 8))
        return elements

    def _build_image_gallery_section(self, title: str, images: List[bytes], max_items: int = 4) -> List[Any]:
        """Render a compact gallery for technical diagrams."""
        usable_images = [image for image in images[:max_items] if image]
        if not usable_images:
            return []

        elements = [self._create_section_header(title), Spacer(1, 4)]
        cards = []
        row = []
        for image_bytes in usable_images:
            try:
                pil_img = PILImage.open(io.BytesIO(image_bytes))
                orig_width, orig_height = pil_img.size
                max_width = self.content_width * 0.45
                max_height = 140
                scale = min(max_width / orig_width, max_height / orig_height, 1)
                card_image = Image(io.BytesIO(image_bytes), width=orig_width * scale, height=orig_height * scale)
                row.append(card_image)
            except Exception:
                row.append(Paragraph("Image unavailable", self.styles['SmallText']))

            if len(row) == 2:
                cards.append(row)
                row = []

        if row:
            while len(row) < 2:
                row.append(Paragraph("", self.styles['SmallText']))
            cards.append(row)

        gallery = Table(cards, colWidths=[self.content_width * 0.5, self.content_width * 0.5])
        gallery.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(gallery)
        elements.append(Spacer(1, 8))
        return elements

    def _build_wiring_section(self, tds_data: IKIOTDSData) -> List[Any]:
        images = [
            item.get("image_data")
            for item in (tds_data.wiring_diagrams or [])
            if isinstance(item, dict) and item.get("image_data")
        ]
        title = self._section_label(tds_data, "wiring_diagram", "Wiring Diagram")
        return self._build_image_gallery_section(title, images)

    def _build_surface_mounting_section(self, tds_data: IKIOTDSData) -> List[Any]:
        images = [
            getattr(item, "image_data", None)
            for item in (tds_data.mounting_options or [])
            if getattr(item, "image_data", None)
        ]
        title = self._section_label(tds_data, "surface_mounting", "Surface Mounting")
        return self._build_image_gallery_section(title, images)

    def _build_certifications_section(self, certifications: List[str]) -> List[Any]:
        """Build certifications section"""
        elements = []
        
        if not certifications:
            return elements
        
        elements.append(self._create_section_header("Certifications"))
        elements.append(Spacer(1, 4))
        
        cert_text = " | ".join(certifications)
        elements.append(Paragraph(cert_text, self.styles['BodyText']))
        
        elements.append(Spacer(1, 6))
        return elements

    def _build_accessories_section(self, accessories: List[TDSAccessory]) -> List[Any]:
        """Build accessories section with simple cards."""
        elements = []

        if not accessories:
            return elements

        elements.append(self._create_section_header("Accessories"))
        elements.append(Spacer(1, 4))

        def build_card(acc: TDSAccessory):
            parts = []
            if acc.image_data:
                try:
                    pil_img = PILImage.open(io.BytesIO(acc.image_data))
                    orig_width, orig_height = pil_img.size
                    max_width = self.content_width * 0.4
                    max_height = 90
                    scale = min(max_width / orig_width, max_height / orig_height, 1)
                    new_width = orig_width * scale
                    new_height = orig_height * scale
                    img_io = io.BytesIO(acc.image_data)
                    parts.append(Image(img_io, width=new_width, height=new_height))
                except Exception:
                    parts.append(Paragraph("Image unavailable", self.styles['SmallText']))
            else:
                parts.append(Paragraph("Image unavailable", self.styles['SmallText']))

            name = acc.name or ""
            sku = acc.sku or acc.part_number or ""
            code = acc.code or ""
            download = acc.download or ""

            text_lines = [
                Paragraph(f"<b>{name}</b>", self.styles['TableCell']),
                Paragraph(f"SKU#: {sku}" if sku else "", self.styles['TableCell']),
                Paragraph(f"Code: {code}" if code else "", self.styles['TableCell']),
                Paragraph("Download" if download else "", self.styles['TableCell']),
            ]
            card = Table([[parts[0]], [text_lines[0]], [text_lines[1]], [text_lines[2]], [text_lines[3]]], colWidths=[self.content_width * 0.45])
            card.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('BOX', (0, 0), (-1, -1), 0.5, BrandColors.TABLE_BORDER),
            ]))
            return card

        rows = []
        row = []
        for acc in accessories:
            row.append(build_card(acc))
            if len(row) == 2:
                rows.append(row)
                row = []
        if row:
            while len(row) < 2:
                row.append(Paragraph("", self.styles['SmallText']))
            rows.append(row)

        grid = Table(rows, colWidths=[self.content_width * 0.5, self.content_width * 0.5])
        grid.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(grid)
        elements.append(Spacer(1, 8))

        return elements

    def _build_notes_section(self, notes: List[str]) -> List[Any]:
        """Build notes section"""
        elements = []
        
        if not notes:
            return elements
        
        elements.append(self._create_section_header("Notes"))
        elements.append(Spacer(1, 4))
        
        for note in notes:
            # Skip warranty notes (already in warranty section)
            if 'warranty' not in note.lower()[:50]:
                elements.append(Paragraph(f"- {note}", self.styles['SmallText']))
        
        elements.append(Spacer(1, 6))
        return elements

    def _generate_content_pdf(self, tds_data: IKIOTDSData) -> bytes:
        """
        Generate content PDF with structured layout matching demo.pdf:
        
        PAGE 1:
        - Part Number + Product Title + Image (header row)
        - Product Description
        - Features  
        - Overview (key specs table)
        - Application Area
        - Warranty
        
        PAGE 2:
        - Product Specifications (from spec_tables)
        
        PAGE 3:
        - Dimensions (with diagram)
        
        PAGE 4+:
        - Distributions (IES diagrams)
        - Certifications
        - Accessories
        - Notes
        """
        buffer = io.BytesIO()
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=(self.page_width, self.page_height),
            leftMargin=self.margin_left,
            rightMargin=self.margin_right,
            topMargin=26 * mm,
            bottomMargin=self.margin_bottom
        )
        
        elements = []

        has_product_specs = any([
            tds_data.power_factor, tds_data.thd, tds_data.beam_angle, tds_data.dimming,
            tds_data.operating_temp, tds_data.suitable_location, tds_data.ip_rating,
            tds_data.ik_rating, tds_data.lifespan, tds_data.warranty_years,
            tds_data.led_light_source, tds_data.housing_material, tds_data.lens_material,
            tds_data.diffuser, tds_data.power_supply, tds_data.finish,
        ])
        has_performance_table = bool(tds_data.performance_table and tds_data.performance_table.rows)

        page_two_elements = []
        if has_performance_table:
            page_two_elements.extend(self._build_secondary_page_intro(tds_data))
            page_two_elements.extend(self._build_spec_table_section(
                tds_data.performance_table,
                title_override=self._section_label(tds_data, "performance_data", "Product Specifications")
            ))
        elif has_product_specs:
            page_two_elements.extend(self._build_secondary_page_intro(tds_data))
            page_two_elements.extend(self._build_product_specs_grid(tds_data))

        has_ordering_content = bool(
            getattr(tds_data, "ordering_info", None)
            or getattr(getattr(tds_data, "ordering_structure", None), "components", None)
        )
        if has_ordering_content:
            if not page_two_elements:
                page_two_elements.extend(self._build_secondary_page_intro(tds_data))
            page_two_elements.extend(self._build_ordering_info_table(tds_data))

        photometrics_elements = self._build_photometrics_section(tds_data)
        if photometrics_elements:
            if not page_two_elements:
                page_two_elements.extend(self._build_secondary_page_intro(tds_data))
            page_two_elements.extend(photometrics_elements)

        has_dimensions = any([
            tds_data.product_length, tds_data.product_width, tds_data.product_height,
            tds_data.dimension_diagram_data, tds_data.net_weight,
            tds_data.slip_fitter_length, tds_data.slip_fitter_width, tds_data.slip_fitter_height
        ])
        page_four_elements = []
        wiring_elements = self._build_wiring_section(tds_data)
        if wiring_elements:
            if not page_four_elements:
                page_four_elements.extend(self._build_secondary_page_intro(tds_data))
            page_four_elements.extend(wiring_elements)
        mounting_elements = self._build_surface_mounting_section(tds_data)
        if mounting_elements:
            if not page_four_elements:
                page_four_elements.extend(self._build_secondary_page_intro(tds_data))
            page_four_elements.extend(mounting_elements)
        accessories_elements = self._build_accessories_section(tds_data.accessories)
        if accessories_elements:
            if not page_four_elements:
                page_four_elements.extend(self._build_secondary_page_intro(tds_data))
            page_four_elements.extend(accessories_elements)

        has_followup_content = bool(page_two_elements or has_dimensions or page_four_elements)

        if has_followup_content:
            elements.append(Spacer(1, 1))
            elements.append(PageBreak())

        if page_two_elements:
            elements.extend(page_two_elements)

        if has_dimensions:
            if page_two_elements:
                elements.append(PageBreak())
            elements.extend(self._build_secondary_page_intro(tds_data))
            elements.extend(self._build_dimensions_section(tds_data))
        else:
            if not elements:
                elements.append(Spacer(1, 1))

        if page_four_elements:
            elements.extend(page_four_elements)

        doc.build(elements)
        return buffer.getvalue()

    def _merge_with_template(self, content_pdf_bytes: bytes, output_path: str, tds_data: IKIOTDSData) -> str:
        """
        Merge generated content with IKIO template PDF.
        Page 1 is drawn directly on the template (header/footer/section headings).
        Remaining pages keep the template background with generated content.
        """
        if not Path(self.template_path).exists():
            print(f"Warning: Template not found at {self.template_path}. Generating without template.")
            with open(output_path, 'wb') as f:
                f.write(content_pdf_bytes)
            return output_path
        
        template_doc = fitz.open(self.template_path)
        content_doc = fitz.open(stream=content_pdf_bytes, filetype="pdf")
        output_doc = fitz.open()

        tpl_count = len(template_doc)
        tpl_first_rect = template_doc[0].rect

        # ----- Page 1: render directly on template -----
        first_page = output_doc.new_page(width=tpl_first_rect.width, height=tpl_first_rect.height)
        first_page.show_pdf_page(first_page.rect, template_doc, 0)
        self._render_template_page1(first_page, tds_data)

        # ----- Remaining pages -----
        for page_num in range(1, len(content_doc)):
            content_page_index = page_num
            tpl_index = min(page_num, tpl_count - 1)
            new_page = output_doc.new_page(
                width=tpl_first_rect.width,
                height=tpl_first_rect.height
            )

            new_page.show_pdf_page(new_page.rect, template_doc, tpl_index)
            try:
                self._stamp_template_header_footer(new_page, tds_data, page_num + 1)
            except Exception as e:
                print(f"Warning: could not stamp header on page {page_num + 1} ({e})")

            new_page.show_pdf_page(new_page.rect, content_doc, content_page_index)

        output_doc.save(output_path)

        template_doc.close()
        content_doc.close()
        output_doc.close()
        return output_path

    def generate_tds(self, tds_data: IKIOTDSData, output_path: str = None, open_after: bool = False) -> str:
        """
        Generate a complete TDS PDF using IKIO template
        """
        self.tds_data = tds_data
        
        # Create output directory
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            product_name_clean = "".join(c for c in tds_data.product_name if c.isalnum() or c in " -_")[:30]
            output_filename = f"TDS_{product_name_clean.replace(' ', '_')}_{timestamp}.pdf"
            output_path = str(OUTPUT_DIR / output_filename)
        
        # Generate content PDF
        content_pdf_bytes = self._generate_content_pdf(tds_data)
        
        # Merge with template
        final_path = self._merge_with_template(content_pdf_bytes, output_path, tds_data)
        
        print(f"[OK] TDS generated successfully: {final_path}")
        
        # Optionally open in system PDF editor/viewer (e.g., Adobe Acrobat)
        if open_after:
            self._open_pdf(final_path)
        
        return final_path


def generate_tds_from_data(tds_data: IKIOTDSData, output_path: str = None, open_after: bool = False) -> str:
    """Convenience function to generate TDS from data"""
    generator = IKIOTDSGenerator()
    return generator.generate_tds(tds_data, output_path, open_after)


def generate_tds(tds_data: IKIOTDSData, output_path: str = None, open_after: bool = False) -> str:
    """Generate a TDS PDF from IKIOTDSData using the IKIO template."""
    generator = IKIOTDSGenerator()
    return generator.generate_tds(tds_data, output_path, open_after)


def generate_demo_tds(output_path: str = None, open_after: bool = False) -> str:
    """Generate a demo TDS for testing"""
    
    demo_data = IKIOTDSData(
        product_name="Post Top- Four Panel Light",
        product_category="LED POST TOP",
        model_number="IK-FP-100W-30K-T2-PC",
        product_description="IKIO's Post Top Light is designed to enhance outdoor spaces with reliable, "
                          "uniform illumination and modern styling. Its durable construction and "
                          "optimized optical performance ensure consistent lighting for pathways, "
                          "streetscapes, and public areas. The fixture supports stable operation in "
                          "varied environments while maintaining an attractive aesthetic suited for "
                          "contemporary and traditional settings. Engineered for longevity and "
                          "minimal maintenance, it provides dependable lighting that improves "
                          "visibility, safety, and overall ambience in outdoor applications.",
        wattage="100W",
        input_voltage="120-277V",
        lumens="10400lm",
        efficacy="104lm/W",
        cct="3000K",
        ip_rating="IP65",
        housing_material="Die-cast Aluminum",
        lens_material="Polycarbonate",
        dimensions='15.75" x 25.74"',
        product_weight="17.64 lbs",
        packaging_dimensions='1.62" x 1.62" x 3.35"',
        box_weight="22.05 lbs",
        warranty="5 Years",
        features=[
            "Robust housing designed for long-term outdoor performance and environmental durability.",
            "Optimized optics deliver uniform, glare-controlled illumination across wide areas.",
            "Seamless, enclosed design supports reduced maintenance and extended service reliability.",
            "Stable light output enhances visibility and safety in public outdoor spaces.",
            "Versatile aesthetic complements both traditional and modern outdoor environments."
        ],
        applications=[
            "Parks",
            "Pedestrian Pathways", 
            "Residential Streets",
            "Campuses",
            "Commercial Outdoor Spaces"
        ],
        certifications=["cETLus", "DLC Listed", "RoHS", "FCC"],
    )
    
    generator = IKIOTDSGenerator()
    return generator.generate_tds(demo_data, output_path, open_after)


# For CLI usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        output = generate_demo_tds()
        print(f"Demo TDS generated: {output}")
    else:
        print("Usage: python pdf_generator.py demo")
