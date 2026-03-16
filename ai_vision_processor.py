"""
AI Vision Processor for Vendor Spec Sheet Extraction
Uses FREE AI providers: Groq, Google Gemini, or Ollama (local)
"""
import json
import base64
import io
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from PIL import Image
import fitz  # PyMuPDF  # type: ignore
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import AI_PROMPTS, TEMP_DIR, SPEC_CATEGORIES
from ai_client import get_ai_client, AIClient

console = Console()


def is_english_text(text: str) -> bool:
    """
    Check if text is primarily English (ASCII/Latin characters).
    Returns True if the text is mostly English, False otherwise.
    """
    if not text or not isinstance(text, str):
        return True
    
    # Count non-ASCII characters (excluding common symbols and numbers)
    non_english_chars = 0
    english_chars = 0
    
    for char in text:
        # Skip whitespace, numbers, and common punctuation
        if char.isspace() or char.isdigit() or char in '.,;:!?-()[]{}\'\"@#$%^&*+=/<>|\\~`°±×÷':
            continue
        
        # Check if character is in basic Latin or Latin Extended blocks
        category = unicodedata.category(char)
        try:
            name = unicodedata.name(char, '')
            if 'LATIN' in name or 'DIGIT' in name:
                english_chars += 1
            elif 'CJK' in name or 'HANGUL' in name or 'ARABIC' in name or 'CYRILLIC' in name or 'DEVANAGARI' in name:
                non_english_chars += 1
            elif ord(char) > 127 and category.startswith('L'):
                # Non-ASCII letter - likely non-English
                non_english_chars += 1
            else:
                english_chars += 1
        except:
            if ord(char) < 128:
                english_chars += 1
            else:
                non_english_chars += 1
    
    total_chars = english_chars + non_english_chars
    if total_chars == 0:
        return True
    
    # If more than 30% non-English characters, consider it non-English
    return (non_english_chars / total_chars) < 0.3


def filter_english_only(text: str) -> str:
    """
    Remove non-English text segments from a string.
    Keeps English text, numbers, and common symbols.
    """
    if not text or not isinstance(text, str):
        return text
    
    # If the whole text is mostly English, return as-is
    if is_english_text(text):
        return text
    
    # Otherwise, filter character by character, keeping English and common chars
    result = []
    for char in text:
        if ord(char) < 128:  # ASCII characters
            result.append(char)
        elif char in '°±×÷²³μΩ':  # Common technical symbols
            result.append(char)
    
    return ''.join(result).strip()


def clean_extracted_data(data: Any) -> Any:
    """
    Recursively clean extracted data to remove non-English content.
    Works with dictionaries, lists, and strings.
    """
    if isinstance(data, str):
        # Filter out non-English text
        cleaned = filter_english_only(data)
        return cleaned if cleaned else None
    
    elif isinstance(data, dict):
        cleaned_dict = {}
        for key, value in data.items():
            cleaned_value = clean_extracted_data(value)
            # Only include if the cleaned value is not empty
            if cleaned_value is not None and cleaned_value != '' and cleaned_value != []:
                cleaned_dict[key] = cleaned_value
        return cleaned_dict
    
    elif isinstance(data, list):
        cleaned_list = []
        for item in data:
            cleaned_item = clean_extracted_data(item)
            # Only include if the cleaned item is not empty
            if cleaned_item is not None and cleaned_item != '' and cleaned_item != {}:
                cleaned_list.append(cleaned_item)
        return cleaned_list
    
    else:
        # Return other types as-is (numbers, booleans, None)
        return data


@dataclass
class ExtractedImage:
    """Represents an extracted image from vendor PDF"""
    page_number: int
    image_data: bytes
    image_type: str  # "dimension", "beam_pattern", "wiring", "mounting", "product", "accessory"
    description: str = ""
    width: int = 0
    height: int = 0


@dataclass
class ExtractedTable:
    """Represents an extracted table from vendor PDF"""
    page_number: int
    title: str
    headers: List[str]
    rows: List[List[str]]
    table_type: str = ""  # "specs", "ordering", "accessories"


@dataclass
class VendorSpecData:
    """Complete extracted data from vendor specification sheet"""
    # Product Information
    product_name: str = ""
    product_series: str = ""
    model_numbers: List[str] = field(default_factory=list)
    product_category: str = ""
    product_description: str = ""
    tagline: str = ""
    
    # Features and Applications
    features: List[str] = field(default_factory=list)
    applications: List[str] = field(default_factory=list)
    variants: List[Dict[str, Any]] = field(default_factory=list)
    
    # Technical Specifications (organized by category)
    electrical_specs: Dict[str, Any] = field(default_factory=dict)
    optical_specs: Dict[str, Any] = field(default_factory=dict)
    physical_specs: Dict[str, Any] = field(default_factory=dict)
    environmental_specs: Dict[str, Any] = field(default_factory=dict)
    lifespan_specs: Dict[str, Any] = field(default_factory=dict)
    component_specs: Dict[str, Any] = field(default_factory=dict)
    
    # Packaging
    packaging_info: Dict[str, str] = field(default_factory=dict)
    
    # Ordering Information
    ordering_info: Dict[str, Any] = field(default_factory=dict)
    part_number_structure: str = ""
    
    # Certifications
    certifications: List[str] = field(default_factory=list)
    
    # Accessories
    accessories_included: List[Dict[str, str]] = field(default_factory=list)
    accessories_sold_separately: List[Dict[str, str]] = field(default_factory=list)
    mounting_options: List[Dict[str, str]] = field(default_factory=list)
    
    # Images and Diagrams
    images: List[ExtractedImage] = field(default_factory=list)
    dimension_diagram: Optional[ExtractedImage] = None
    beam_angle_diagrams: List[ExtractedImage] = field(default_factory=list)
    wiring_diagrams: List[ExtractedImage] = field(default_factory=list)
    
    # Raw Tables for Reference
    raw_tables: List[ExtractedTable] = field(default_factory=list)
    
    # Metadata
    source_file: str = ""
    page_count: int = 0
    extraction_confidence: float = 0.0


class AIVisionProcessor:
    """
    AI-powered processor that uses FREE AI providers to extract 
    comprehensive data from vendor specification sheets.
    
    Supported providers:
    - Groq (FREE, fast, text-only)
    - Google Gemini (FREE, vision support)
    - Ollama (FREE, local, vision with LLaVA)
    """
    
    def __init__(self, provider: Optional[str] = None, api_key: Optional[str] = None):
        self.client = get_ai_client(provider, api_key)  # type: ignore
        self.use_vision = self.client.supports_vision
        
        console.print(f"[green]✓ AI Client: {type(self.client).__name__}[/green]")
        console.print(f"[green]✓ Vision support: {self.use_vision}[/green]")
    
    def process_vendor_pdf(self, pdf_path: str) -> VendorSpecData:
        """
        Main method to process a vendor PDF and extract all data.
        Uses vision if available, otherwise falls back to text extraction.
        """
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        console.print(f"[cyan]Processing vendor PDF: {pdf_path_obj.name}[/cyan]")
        
        # Initialize extracted data
        extracted_data = VendorSpecData(
            source_file=str(pdf_path_obj)
        )
        
        # Get page count
        doc = fitz.open(pdf_path_obj)
        extracted_data.page_count = len(doc)
        doc.close()
        
        if self.use_vision:
            # Use vision-based extraction
            extracted_data = self._process_with_vision(pdf_path_obj, extracted_data)
        else:
            # Use text-based extraction (for Groq)
            extracted_data = self._process_with_text(pdf_path_obj, extracted_data)
        
        # Extract images regardless of AI mode
        extracted_data = self._extract_all_images(pdf_path_obj, extracted_data)
        
        # Classify images
        self._classify_images(extracted_data)
        
        # Calculate confidence score
        extracted_data.extraction_confidence = self._calculate_confidence(extracted_data)
        
        console.print(f"[green]✓ Extraction complete! Confidence: {extracted_data.extraction_confidence:.1%}[/green]")
        
        return extracted_data
    
    def _process_with_vision(self, pdf_path: Path, extracted_data: VendorSpecData) -> VendorSpecData:
        """Process PDF using AI vision (Gemini, Ollama/LLaVA)"""
        console.print("[cyan]Using AI Vision for extraction...[/cyan]")
        
        # Convert PDF pages to images
        page_images = self._pdf_to_images(pdf_path)
        console.print(f"[green]✓ Converted {len(page_images)} pages to images[/green]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(
                f"Analyzing {len(page_images)} pages with AI Vision...", 
                total=len(page_images)
            )
            
            all_page_data = []
            for page_num, image_data in page_images:
                progress.update(task, description=f"Analyzing page {page_num}...")
                
                # Analyze page with vision
                page_analysis = self.client.analyze_image(image_data, prompt=None)
                page_analysis["page"] = page_num
                all_page_data.append(page_analysis)
                
                progress.advance(task)
        
        # Consolidate all page data
        return self._consolidate_extracted_data(all_page_data, extracted_data)
    
    def _process_with_text(self, pdf_path: Path, extracted_data: VendorSpecData) -> VendorSpecData:
        """Process PDF using text extraction (for Groq and other text-only models)"""
        console.print("[cyan]Using text extraction mode (vision not available)...[/cyan]")
        
        # Extract all text from PDF
        doc = fitz.open(pdf_path)
        all_text = []
        page_texts = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            page_texts.append(text)
            all_text.append(f"\n--- Page {page_num + 1} ---\n{text}")
        
        doc.close()
        
        full_text = "\n".join(all_text)
        console.print(f"[green]✓ Extracted {len(full_text)} characters of text[/green]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Analyzing text with AI...", total=None)
            
            # Analyze full text
            analysis = self.client.analyze_text(full_text, prompt=None)
            progress.update(task, description="Analysis complete!")
        
        fallback_analysis = self._build_fallback_text_analysis(page_texts, pdf_path)
        consolidated_inputs = []
        if fallback_analysis:
            consolidated_inputs.append(fallback_analysis)
        if isinstance(analysis, dict):
            consolidated_inputs.append(analysis)

        return self._consolidate_extracted_data(consolidated_inputs, extracted_data)

    def _normalize_pdf_line(self, value: str) -> str:
        text = unicodedata.normalize("NFKC", str(value or ""))
        text = text.replace("\xa0", " ").replace("â€¢", " ").replace("•", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _split_text_lines(self, text: str) -> List[str]:
        lines = []
        for raw_line in str(text or "").splitlines():
            cleaned = self._normalize_pdf_line(raw_line)
            if not cleaned or cleaned.startswith("--- Page "):
                continue
            lines.append(cleaned)
        return lines

    def _find_line(self, lines: List[str], labels: Union[str, List[str], Tuple[str, ...]]) -> int:
        if isinstance(labels, str):
            labels = [labels]
        normalized = [self._normalize_pdf_line(label).lower() for label in labels if self._normalize_pdf_line(label)]
        for index, line in enumerate(lines):
            current = self._normalize_pdf_line(line).lower()
            if current in normalized:
                return index
        for index, line in enumerate(lines):
            current = self._normalize_pdf_line(line).lower()
            if any(current.startswith(label) for label in normalized):
                return index
        return -1

    def _collect_after_label(
        self,
        lines: List[str],
        labels: Union[str, List[str], Tuple[str, ...]],
        stop_labels: List[str],
        max_lines: Optional[int] = None,
    ) -> List[str]:
        start_index = self._find_line(lines, labels)
        if start_index < 0:
            return []

        stop_set = {self._normalize_pdf_line(label).lower() for label in stop_labels if self._normalize_pdf_line(label)}
        values: List[str] = []
        for line in lines[start_index + 1:]:
            current = self._normalize_pdf_line(line)
            if not current:
                continue
            if current.lower() in stop_set:
                break
            values.append(current)
            if max_lines is not None and len(values) >= max_lines:
                break
        return values

    def _join_values(self, values: List[str], separator: str = " / ") -> str:
        cleaned = [self._normalize_pdf_line(value) for value in values if self._normalize_pdf_line(value)]
        return separator.join(cleaned)

    def _extract_section_items(
        self,
        lines: List[str],
        labels: Union[str, List[str], Tuple[str, ...]],
        stop_labels: List[str],
    ) -> List[str]:
        items = []
        for value in self._collect_after_label(lines, labels, stop_labels):
            cleaned = self._normalize_pdf_line(re.sub(r"^[\*\-\u2022]+\s*", "", value))
            lowered = cleaned.lower()
            if not cleaned:
                continue
            if lowered in {"new features", "description", "dimensions and mount", "dimentions and mount"}:
                continue
            if "please consult us" in lowered or lowered.startswith("www.") or "data subject to change" in lowered:
                break
            items.append(cleaned)
        return items

    def _guess_product_category(self, title: str, full_text: str) -> str:
        search_text = f"{title} {full_text}".lower()
        if "flood light" in search_text or "sports light" in search_text:
            return "Flood Light"
        if "street light" in search_text:
            return "Street Light"
        if "high bay" in search_text:
            return "High Bay"
        if "area light" in search_text or "area luminaire" in search_text:
            return "Area Luminaire"
        return "LED Lighting Product"

    def _guess_title_from_lines(self, lines: List[str]) -> str:
        skip_prefixes = (
            "version",
            "electrical information",
            "optic information",
            "lifespan and warranty",
            "applications",
            "photometry",
            "dimensions",
            "accessories",
            "mounting options",
            "data subject to change",
            "www.",
        )
        for line in lines:
            cleaned = self._normalize_pdf_line(line)
            lowered = cleaned.lower()
            if not cleaned:
                continue
            if lowered.startswith(skip_prefixes):
                continue
            if re.fullmatch(r"tmp[\w\-]+", lowered):
                continue
            if re.search(r"(product|lighting|light|luminaire)", lowered):
                return cleaned
        return ""

    def _build_fallback_text_analysis(self, page_texts: List[str], pdf_path: Path) -> Dict[str, Any]:
        if not page_texts:
            return {}

        first_page_lines = self._split_text_lines(page_texts[0])
        full_text = "\n".join(page_texts)
        full_search = self._normalize_pdf_line(full_text)

        stop_labels = [
            "Version:",
            "Electrical Information",
            "Model No.",
            "Power Consumption (±10%)",
            "Power Consumption (10%)",
            "Power Supply",
            "Input Voltage",
            "Power Factor",
            "Surge Protection",
            "Driver Type",
            "Control",
            "Optic Information",
            "LED Type",
            "Luminous Flux (±10%)",
            "Luminous Flux (10%)",
            "Efficacy (5000K Ra70)",
            "Correlated Color Temperature",
            "Color Rendering Index",
            "Beam Angle",
            "Description",
            "Dimentions and Mount",
            "Product Dimension",
            "Net Weight",
            "Export Carton Size",
            "Gross Weight",
            "Mounting Option",
            "Material",
            "Key Features",
            "Finish",
            "Fixture Color",
            "EPA",
            "IK Rating",
            "IP Rating",
            "Categoryofcorrosion",
            "Category of corrosion",
            "Lifespan and Warranty",
            "Operating Temperature",
            "Life Time of LED @Ta=25°C",
            "Life Time of LED @Ta=25C",
            "Warranty",
            "Applications",
            "Applications ",
        ]

        title_match = re.search(r"Specifications\s*-\s*(.+)", page_texts[0], re.IGNORECASE)
        raw_title = self._normalize_pdf_line(title_match.group(1) if title_match else "")
        if not raw_title:
            raw_title = self._guess_title_from_lines(first_page_lines)
        model_numbers = self._collect_after_label(first_page_lines, "Model No.", stop_labels, max_lines=8)

        series = ""
        for model in model_numbers:
            match = re.search(r"\b([A-Z]{2,}\d{2,})\b", model.upper())
            if match:
                series = match.group(1)
                break

        if not raw_title:
            raw_title = f"{series} LED Lighting Product".strip() if series else "IKIO Product"

        product_description_lines = self._collect_after_label(
            first_page_lines,
            "Description",
            stop_labels,
        )
        product_description = " ".join(
            line
            for line in product_description_lines
            if line.lower() not in {"dimentions and mount", "dimensions and mount"}
        ).strip()

        key_feature_lines = self._collect_after_label(first_page_lines, "Key Features", stop_labels)
        lens_material = ""
        if key_feature_lines and "lens" in key_feature_lines[0].lower():
            lens_material = key_feature_lines[0]
            key_feature_lines = key_feature_lines[1:]
        features = [
            self._normalize_pdf_line(re.sub(r"^[\*\-\u2022]+\s*", "", feature))
            for feature in key_feature_lines
            if self._normalize_pdf_line(re.sub(r"^[\*\-\u2022]+\s*", "", feature))
        ]

        applications = self._extract_section_items(first_page_lines, ["Applications", "Applications "], stop_labels)

        product_category = self._guess_product_category(raw_title, full_text)
        product_name = raw_title or f"{series} LED Lighting Product".strip()

        electrical_specs: Dict[str, Any] = {}
        component_specs: Dict[str, Any] = {}
        optical_specs: Dict[str, Any] = {}
        physical_specs: Dict[str, Any] = {}
        environmental_specs: Dict[str, Any] = {}
        lifespan_specs: Dict[str, Any] = {}

        power_lines = self._collect_after_label(
            first_page_lines,
            ["Power Consumption (±10%)", "Power Consumption (10%)"],
            stop_labels,
            max_lines=max(4, len(model_numbers) or 0),
        )
        power = self._join_values(power_lines)
        if power:
            electrical_specs["Power Consumption"] = power

        input_voltage = self._join_values(self._collect_after_label(first_page_lines, "Input Voltage", stop_labels, max_lines=2))
        if input_voltage:
            electrical_specs["Input Voltage"] = input_voltage

        power_factor = self._join_values(self._collect_after_label(first_page_lines, "Power Factor", stop_labels, max_lines=1))
        if power_factor:
            electrical_specs["Power Factor"] = power_factor

        surge = self._join_values(self._collect_after_label(first_page_lines, "Surge Protection", stop_labels, max_lines=2))
        if surge:
            electrical_specs["Surge Protection"] = surge

        control = self._join_values(self._collect_after_label(first_page_lines, "Control", stop_labels, max_lines=4))
        if control:
            electrical_specs["Control"] = control

        power_supply = self._join_values(self._collect_after_label(first_page_lines, "Power Supply", stop_labels, max_lines=2))
        if power_supply:
            component_specs["Power Supply"] = power_supply

        driver_type = self._join_values(self._collect_after_label(first_page_lines, "Driver Type", stop_labels, max_lines=2))
        if driver_type:
            component_specs["Driver Type"] = driver_type

        led_type = self._join_values(self._collect_after_label(first_page_lines, "LED Type", stop_labels, max_lines=2))
        if led_type:
            optical_specs["LED Type"] = led_type

        luminous_flux_lines = self._collect_after_label(
            first_page_lines,
            ["Luminous Flux (±10%)", "Luminous Flux (10%)"],
            stop_labels,
            max_lines=max(4, len(model_numbers) or 0),
        )
        luminous_flux = self._join_values(luminous_flux_lines)
        if luminous_flux:
            optical_specs["Luminous Flux"] = luminous_flux

        efficacy_lines = self._collect_after_label(
            first_page_lines,
            "Efficacy (5000K Ra70)",
            stop_labels,
            max_lines=max(2, len(model_numbers) or 0),
        )
        efficacy = self._join_values(efficacy_lines)
        if efficacy:
            optical_specs["Efficacy"] = efficacy

        cct = self._join_values(self._collect_after_label(first_page_lines, "Correlated Color Temperature", stop_labels, max_lines=2))
        if cct:
            optical_specs["Correlated Color Temperature"] = cct

        cri = self._join_values(self._collect_after_label(first_page_lines, "Color Rendering Index", stop_labels, max_lines=2))
        if cri:
            optical_specs["Color Rendering Index"] = cri

        beam_angle = self._join_values(self._collect_after_label(first_page_lines, "Beam Angle", stop_labels, max_lines=2))
        if beam_angle:
            optical_specs["Beam Angle"] = beam_angle

        dimensions = self._join_values(self._collect_after_label(first_page_lines, "Product Dimension", stop_labels, max_lines=2), separator=" ")
        if dimensions:
            physical_specs["Dimensions"] = dimensions

        net_weight = self._join_values(self._collect_after_label(first_page_lines, "Net Weight", stop_labels, max_lines=6))
        if net_weight:
            physical_specs["Net Weight"] = net_weight

        mounting_option = self._join_values(self._collect_after_label(first_page_lines, "Mounting Option", stop_labels, max_lines=2))
        if mounting_option:
            physical_specs["Mounting Option"] = mounting_option

        material = self._join_values(self._collect_after_label(first_page_lines, "Material", stop_labels, max_lines=2))
        if material:
            physical_specs["Material"] = material

        if lens_material:
            physical_specs["Lens Material"] = lens_material

        finish = self._join_values(self._collect_after_label(first_page_lines, "Finish", stop_labels, max_lines=2))
        if finish:
            physical_specs["Finish"] = finish

        fixture_color = self._join_values(self._collect_after_label(first_page_lines, "Fixture Color", stop_labels, max_lines=2))
        if fixture_color:
            physical_specs["Fixture Color"] = fixture_color

        epa = self._join_values(self._collect_after_label(first_page_lines, "EPA", stop_labels, max_lines=2))
        if epa:
            physical_specs["EPA"] = epa

        operating_temp = self._join_values(self._collect_after_label(first_page_lines, "Operating Temperature", stop_labels, max_lines=2))
        if operating_temp:
            environmental_specs["Operating Temperature"] = operating_temp

        ik_rating = self._join_values(self._collect_after_label(first_page_lines, "IK Rating", stop_labels, max_lines=1))
        if ik_rating:
            environmental_specs["IK Rating"] = ik_rating

        ip_rating = self._join_values(self._collect_after_label(first_page_lines, "IP Rating", stop_labels, max_lines=1))
        if ip_rating:
            environmental_specs["IP Rating"] = ip_rating

        corrosion = self._join_values(
            self._collect_after_label(first_page_lines, ["Categoryofcorrosion", "Category of corrosion"], stop_labels, max_lines=1)
        )
        if corrosion:
            environmental_specs["Category of Corrosion"] = corrosion

        lifetime = self._join_values(
            self._collect_after_label(first_page_lines, ["Life Time of LED @Ta=25°C", "Life Time of LED @Ta=25C"], stop_labels, max_lines=6)
        )
        if lifetime:
            lifespan_specs["Life Time"] = lifetime

        warranty = self._join_values(self._collect_after_label(first_page_lines, "Warranty", stop_labels, max_lines=1))
        if warranty:
            lifespan_specs["Warranty"] = warranty

        certifications = []
        for marker in (
            environmental_specs.get("IP Rating", ""),
            environmental_specs.get("IK Rating", ""),
        ):
            cleaned = self._normalize_pdf_line(marker)
            if cleaned and cleaned not in certifications:
                certifications.append(cleaned)

        for label in ("DLC Premium", "DLC", "ETL", "UL", "RoHS", "Energy Star"):
            if self._normalize_pdf_line(label).lower() in full_search.lower() and label not in certifications:
                certifications.append(label)

        if control and not any("dimmable" in feature.lower() for feature in features):
            features.append(f"{control} control compatibility")

        variants = []
        if model_numbers:
            def align_variant_values(values: List[str], count: int) -> List[str]:
                cleaned = [self._normalize_pdf_line(value) for value in values if self._normalize_pdf_line(value)]
                if not cleaned:
                    return [""] * count
                if len(cleaned) >= count:
                    return cleaned[:count]
                if len(cleaned) == 1:
                    return cleaned * count
                return cleaned + [cleaned[-1]] * (count - len(cleaned))

            variant_count = len(model_numbers)
            aligned_power = align_variant_values(power_lines, variant_count)
            aligned_lumens = align_variant_values(luminous_flux_lines, variant_count)
            aligned_efficacy = align_variant_values(efficacy_lines, variant_count)

            for index, model in enumerate(model_numbers):
                variants.append({
                    "part_number": model,
                    "model": model,
                    "power": aligned_power[index] if index < len(aligned_power) else "",
                    "voltage": input_voltage,
                    "lumens": aligned_lumens[index] if index < len(aligned_lumens) else "",
                    "efficacy": aligned_efficacy[index] if index < len(aligned_efficacy) else efficacy,
                    "cri": cri,
                    "current": "",
                    "cct": cct,
                    "thd": electrical_specs.get("THD", ""),
                    "light_distribution": "",
                })

        fallback_analysis: Dict[str, Any] = {
            "product_info": {
                "name": product_name,
                "series": series,
                "model": model_numbers,
                "category": product_category,
                "description": product_description,
            },
            "features": features,
            "applications": applications,
            "electrical_specs": electrical_specs,
            "optical_specs": optical_specs,
            "physical_specs": physical_specs,
            "environmental_specs": environmental_specs,
            "lifespan_specs": lifespan_specs,
            "component_specs": component_specs,
            "certifications": certifications,
            "variants": variants,
        }

        return clean_extracted_data(fallback_analysis) or {}
    
    def _pdf_to_images(self, pdf_path: Path, dpi: int = 150) -> List[Tuple[int, bytes]]:
        """Convert PDF pages to images for vision analysis"""
        page_images = []
        
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Render page to image
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PNG bytes
            img_bytes = pix.tobytes("png")
            page_images.append((page_num + 1, img_bytes))
        
        doc.close()
        return page_images
    
    def _extract_all_images(self, pdf_path: Path, extracted_data: VendorSpecData) -> VendorSpecData:
        """Extract all images from PDF"""
        doc = fitz.open(pdf_path)
        
        # #region agent log
        import json as _json_log
        print(f"[DEBUG] _extract_all_images: Starting extraction from {pdf_path}, pages={len(doc)}")
        try:
            with open(r"c:\Users\IKIO\Desktop\TDS-GENERATOR-13-NOV-2025\mycode\output\debug.log", "a") as _f:
                _f.write(_json_log.dumps({"location":"ai_vision_processor.py:_extract_all_images:entry","message":"Starting image extraction","data":{"pdf_path":str(pdf_path),"page_count":len(doc)},"hypothesisId":"H1","sessionId":"debug-session","timestamp":__import__('time').time()*1000})+"\n")
        except Exception as _e:
            print(f"[DEBUG] Log write failed: {_e}")
        # #endregion
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            # #region agent log
            with open(r"c:\Users\IKIO\Desktop\TDS-GENERATOR-13-NOV-2025\mycode\output\debug.log", "a") as _f:
                _f.write(_json_log.dumps({"location":"ai_vision_processor.py:_extract_all_images:page","message":"Processing page images","data":{"page_num":page_num+1,"image_count":len(image_list)},"hypothesisId":"H1","sessionId":"debug-session","timestamp":__import__('time').time()*1000})+"\n")
            # #endregion
            
            for img_index, img in enumerate(image_list):
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_rects = page.get_image_rects(xref)
                    image_rect = image_rects[0] if image_rects else None
                    nearby_text = self._collect_nearby_text(page, image_rect)
                    
                    # Get image dimensions
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    width, height = pil_image.size
                    
                    # #region agent log
                    with open(r"c:\Users\IKIO\Desktop\TDS-GENERATOR-13-NOV-2025\mycode\output\debug.log", "a") as _f:
                        _f.write(_json_log.dumps({"location":"ai_vision_processor.py:_extract_all_images:image","message":"Found image","data":{"page":page_num+1,"index":img_index,"width":width,"height":height,"size_bytes":len(image_bytes)},"hypothesisId":"H2","sessionId":"debug-session","timestamp":__import__('time').time()*1000})+"\n")
                    # #endregion
                    
                    # Enhanced filtering: Include images that are likely to be useful
                    # More lenient thresholds to capture all relevant images
                    MIN_WIDTH = 48
                    MIN_HEIGHT = 48
                    MIN_TOTAL_PIXELS = 2500
                    context_lower = nearby_text.lower()
                    has_technical_context = any(
                        keyword in context_lower
                        for keyword in (
                            "dimension",
                            "dimensions",
                            "mount",
                            "mounting",
                            "wiring",
                            "wire",
                            "photometric",
                            "distribution",
                            "beam",
                            "candela",
                            "ies",
                            "installation",
                            "diagram",
                            "outline",
                        )
                    )
                    
                    # Include if meets size requirements
                    if has_technical_context or (width >= MIN_WIDTH and height >= MIN_HEIGHT) or (width * height >= MIN_TOTAL_PIXELS):
                        extracted_data.images.append(ExtractedImage(
                            page_number=page_num + 1,
                            image_data=image_bytes,
                            image_type="unknown",
                            description=nearby_text,
                            width=width,
                            height=height
                        ))
                        # #region agent log
                        with open(r"c:\Users\IKIO\Desktop\TDS-GENERATOR-13-NOV-2025\mycode\output\debug.log", "a") as _f:
                            _f.write(_json_log.dumps({"location":"ai_vision_processor.py:_extract_all_images:accepted","message":"Image accepted","data":{"page":page_num+1,"index":img_index,"width":width,"height":height},"hypothesisId":"H3","sessionId":"debug-session","timestamp":__import__('time').time()*1000})+"\n")
                        # #endregion
                    else:
                        # #region agent log
                        with open(r"c:\Users\IKIO\Desktop\TDS-GENERATOR-13-NOV-2025\mycode\output\debug.log", "a") as _f:
                            _f.write(_json_log.dumps({"location":"ai_vision_processor.py:_extract_all_images:filtered","message":"Image filtered (too small)","data":{"page":page_num+1,"index":img_index,"width":width,"height":height,"min_required":f"{MIN_WIDTH}x{MIN_HEIGHT}"},"hypothesisId":"H3","sessionId":"debug-session","timestamp":__import__('time').time()*1000})+"\n")
                        # #endregion
                        pass  # Skip small icons
                except Exception as e:

                    # #region agent log
                    with open(r"c:\Users\IKIO\Desktop\TDS-GENERATOR-13-NOV-2025\mycode\output\debug.log", "a") as _f:
                        _f.write(_json_log.dumps({"location":"ai_vision_processor.py:_extract_all_images:error","message":"Failed to extract image","data":{"page":page_num+1,"index":img_index,"error":str(e)},"hypothesisId":"H1","sessionId":"debug-session","timestamp":__import__('time').time()*1000})+"\n")
                    # #endregion
                    pass  # Skip problematic images
        
        # #region agent log
        print(f"[DEBUG] _extract_all_images: COMPLETE - Found {len(extracted_data.images)} images")
        try:
            with open(r"c:\Users\IKIO\Desktop\TDS-GENERATOR-13-NOV-2025\mycode\output\debug.log", "a") as _f:
                _f.write(_json_log.dumps({"location":"ai_vision_processor.py:_extract_all_images:exit","message":"Image extraction complete","data":{"total_images":len(extracted_data.images)},"hypothesisId":"H1","sessionId":"debug-session","timestamp":__import__('time').time()*1000})+"\n")
        except Exception as _e:
            print(f"[DEBUG] Log write failed: {_e}")
        # #endregion
        
        doc.close()
        return extracted_data

    def _collect_nearby_text(self, page: fitz.Page, rect: Optional[fitz.Rect], padding: float = 30) -> str:
        """Collect nearby words around an image to improve classification."""
        if rect is None:
            return ""

        search_rect = fitz.Rect(
            rect.x0 - padding,
            rect.y0 - padding,
            rect.x1 + padding,
            rect.y1 + padding,
        )
        nearby_words = []
        try:
            for word in page.get_text("words"):
                word_rect = fitz.Rect(word[:4])
                if word_rect.intersects(search_rect):
                    nearby_words.append(str(word[4]))
        except Exception:
            return ""

        return self._normalize_pdf_line(" ".join(nearby_words[:32]))
    
    def _consolidate_extracted_data(
        self, 
        page_data: List[Dict], 
        extracted_data: VendorSpecData
    ) -> VendorSpecData:
        """Consolidate data from multiple pages/analyses into a single structure"""
        
        for page in page_data:
            # Clean the page data to remove non-English content
            page = clean_extracted_data(page)
            if "error" in page and not "raw_content" in page:
                continue
            
            # Extract product info
            if "product_info" in page:
                info = page["product_info"]
                if isinstance(info, dict):
                    if info.get("name") and not extracted_data.product_name:
                        extracted_data.product_name = str(info["name"])
                    if info.get("series"):
                        extracted_data.product_series = str(info["series"])
                    if info.get("model"):
                        models = info["model"]
                        if isinstance(models, list):
                            extracted_data.model_numbers.extend([str(m) for m in models])
                        else:
                            extracted_data.model_numbers.append(str(models))
                    if info.get("category"):
                        extracted_data.product_category = str(info["category"])
                    if info.get("description"):
                        extracted_data.product_description = str(info["description"])
            
            # Try to get product name from various keys
            for key in ["product_name", "name", "title"]:
                if key in page and page[key] and not extracted_data.product_name:
                    extracted_data.product_name = str(page[key])
                    break
            
            # Extract features (only English text)
            features = page.get("features", [])
            if isinstance(features, list):
                for feature in features:
                    feature_str = str(feature) if feature else ""
                    # Only add if it's English text
                    if feature_str and is_english_text(feature_str) and feature_str not in extracted_data.features:
                        extracted_data.features.append(feature_str)
            
            # Extract applications (only English text)
            applications = page.get("applications", page.get("application_areas", []))
            if isinstance(applications, list):
                for app in applications:
                    app_str = str(app) if app else ""
                    # Only add if it's English text
                    if app_str and is_english_text(app_str) and app_str not in extracted_data.applications:
                        extracted_data.applications.append(app_str)

            page_variants = page.get("variants", [])
            if isinstance(page_variants, list):
                existing_keys = {
                    str(item.get("part_number") or item.get("model") or "").strip().lower()
                    for item in extracted_data.variants
                    if isinstance(item, dict)
                }
                for variant in page_variants:
                    if not isinstance(variant, dict):
                        continue
                    key = str(variant.get("part_number") or variant.get("model") or "").strip().lower()
                    if key and key in existing_keys:
                        continue
                    extracted_data.variants.append(variant)
                    if key:
                        existing_keys.add(key)
            
            # Extract specifications by category
            self._merge_specs(page.get("electrical_specs", {}), extracted_data.electrical_specs)
            self._merge_specs(page.get("optical_specs", {}), extracted_data.optical_specs)
            self._merge_specs(page.get("physical_specs", {}), extracted_data.physical_specs)
            self._merge_specs(page.get("environmental_specs", {}), extracted_data.environmental_specs)
            self._merge_specs(page.get("lifespan_specs", {}), extracted_data.lifespan_specs)
            self._merge_specs(page.get("component_specs", {}), extracted_data.component_specs)
            
            # Also check for generic "specifications" key
            if "specifications" in page:
                self._parse_generic_specs(page["specifications"], extracted_data)
            if "technical_specifications" in page:
                self._parse_generic_specs(page["technical_specifications"], extracted_data)
            
            # Extract certifications (only English text)
            certs = page.get("certifications", [])
            if isinstance(certs, list):
                for cert in certs:
                    cert_str = str(cert) if cert else ""
                    # Only add if it's English text
                    if cert_str and is_english_text(cert_str) and cert_str not in extracted_data.certifications:
                        extracted_data.certifications.append(cert_str)
            
            # Extract ordering information
            if "ordering_info" in page and isinstance(page["ordering_info"], dict):
                extracted_data.ordering_info.update(page["ordering_info"])
            if "part_number_structure" in page:
                extracted_data.part_number_structure = str(page["part_number_structure"])
            
            # Extract packaging info
            pkg = page.get("packaging", page.get("packaging_info", {}))
            if isinstance(pkg, dict):
                extracted_data.packaging_info.update(pkg)
            
            # Extract accessories
            accessories = page.get("accessories", {})
            if isinstance(accessories, dict):
                if "included" in accessories:
                    extracted_data.accessories_included.extend(
                        self._normalize_accessories(accessories["included"])
                    )
                if "sold_separately" in accessories:
                    extracted_data.accessories_sold_separately.extend(
                        self._normalize_accessories(accessories["sold_separately"])
                    )
            elif isinstance(accessories, list):
                extracted_data.accessories_sold_separately.extend(
                    self._normalize_accessories(accessories)
                )
            
            # Extract mounting options
            if "mounting_options" in page:
                extracted_data.mounting_options.extend(
                    self._normalize_accessories(page["mounting_options"])
                )
            
            # Extract tables
            if "tables" in page and isinstance(page["tables"], list):
                for table in page["tables"]:
                    if isinstance(table, dict):
                        extracted_data.raw_tables.append(ExtractedTable(
                            page_number=page.get("page", 0),
                            title=table.get("title", ""),
                            headers=table.get("headers", []),
                            rows=table.get("rows", []),
                            table_type=table.get("type", "")
                        ))
        
        # Generate tagline if not found
        if not extracted_data.tagline and extracted_data.product_name:
            extracted_data.tagline = self._generate_tagline(extracted_data)
        
        return extracted_data
    
    def _merge_specs(self, source: Dict, target: Dict):
        """Merge specification dictionaries"""
        if not isinstance(source, dict):
            return
        for key, value in source.items():
            if value and key not in target:
                target[key] = value
            elif value and isinstance(value, dict) and isinstance(target.get(key), dict):
                target[key].update(value)
    
    def _parse_generic_specs(self, specs: Any, extracted_data: VendorSpecData):
        """Parse specifications and categorize them"""
        if not specs:
            return
        
        if isinstance(specs, dict):
            for key, value in specs.items():
                key_lower = key.lower()
                
                # Categorize based on key name
                if any(x in key_lower for x in ['power', 'voltage', 'current', 'watt', 'factor', 'surge', 'thd', 'frequency']):
                    extracted_data.electrical_specs[key] = value
                elif any(x in key_lower for x in ['lumen', 'efficacy', 'cct', 'cri', 'beam', 'angle', 'color temp', 'flux']):
                    extracted_data.optical_specs[key] = value
                elif any(x in key_lower for x in ['dimension', 'weight', 'material', 'housing', 'lens', 'finish', 'epa', 'size']):
                    extracted_data.physical_specs[key] = value
                elif any(x in key_lower for x in ['ip', 'ik', 'temp', 'humidity', 'operating', 'ambient']):
                    extracted_data.environmental_specs[key] = value
                elif any(x in key_lower for x in ['life', 'l70', 'l80', 'warranty', 'hours']):
                    extracted_data.lifespan_specs[key] = value
                elif any(x in key_lower for x in ['led', 'driver', 'chip', 'source', 'supply']):
                    extracted_data.component_specs[key] = value
    
    def _normalize_accessories(self, accessories: Any) -> List[Dict[str, str]]:
        """Normalize accessories to consistent format"""
        result = []
        if isinstance(accessories, list):
            for item in accessories:
                if isinstance(item, str):
                    result.append({"name": item, "description": ""})
                elif isinstance(item, dict):
                    result.append({
                        "name": item.get("name", item.get("title", "")),
                        "description": item.get("description", ""),
                        "image": item.get("image", "")
                    })
        elif isinstance(accessories, dict):
            for name, desc in accessories.items():
                result.append({"name": str(name), "description": str(desc) if desc else ""})
        return result
    
    def _classify_images(self, extracted_data: VendorSpecData):
        """
        Enhanced image classification based on size, aspect ratio, and content analysis.
        Uses AI vision when available to better understand image context.
        """
        # Sort images by size (largest first) to prioritize important diagrams
        sorted_images = sorted(
            extracted_data.images,
            key=lambda img: img.width * img.height,
            reverse=True
        )
        
        for image in sorted_images:
            # Calculate aspect ratio
            aspect_ratio = image.width / max(image.height, 1)
            total_pixels = image.width * image.height
            description = (image.description or "").lower()

            # 0. Prefer explicit nearby-text context over geometry heuristics.
            if any(keyword in description for keyword in ("wiring", "wire diagram", "driver wiring", "schematic")):
                image.image_type = "wiring"
                extracted_data.wiring_diagrams.append(image)
                continue

            if any(keyword in description for keyword in (
                "mounting",
                "mount",
                "slip fitter",
                "surface mount",
                "bracket",
                "installation",
            )):
                image.image_type = "mounting"
                continue

            if any(keyword in description for keyword in (
                "dimension",
                "dimensions",
                "outline",
                "size",
                "diameter",
            )):
                image.image_type = "dimension"
                if not extracted_data.dimension_diagram:
                    extracted_data.dimension_diagram = image
                continue

            if any(keyword in description for keyword in (
                "photometric",
                "distribution",
                "beam",
                "candela",
                "polar",
                "ies",
            )):
                image.image_type = "photometric"
                extracted_data.beam_angle_diagrams.append(image)
                continue
            
            # ENHANCED CLASSIFICATION LOGIC
            # 1. Very wide images (landscape charts/graphs) - likely photometric/beam patterns
            if aspect_ratio > 2.0:
                # Very wide images are almost certainly photometric charts or beam patterns
                image.image_type = "beam_pattern"
                extracted_data.beam_angle_diagrams.append(image)
            
            # 2. Wide images (1.5 - 2.0 aspect ratio) - could be photometric or product images
            elif 1.5 <= aspect_ratio <= 2.0:
                if total_pixels > 50000:  # Large images are likely photometric charts
                    image.image_type = "photometric"
                    extracted_data.beam_angle_diagrams.append(image)
                elif total_pixels > 20000:  # Medium-large could be product images
                    image.image_type = "product"
                else:
                    image.image_type = "product"
            
            # 3. Square-ish images (0.7 - 1.5 aspect ratio) - dimension diagrams or product photos
            elif 0.7 <= aspect_ratio <= 1.5:
                if total_pixels > 40000:  # Large square images
                    if not extracted_data.dimension_diagram:
                        # First large square image is likely dimension diagram
                        image.image_type = "dimension"
                        extracted_data.dimension_diagram = image
                    elif total_pixels > 60000:
                        # Very large square images are likely product photos
                        image.image_type = "product"
                    else:
                        # Could be additional dimension views
                        image.image_type = "dimension"
                elif total_pixels > 15000:  # Medium square images
                    if not extracted_data.dimension_diagram:
                        image.image_type = "dimension"
                        extracted_data.dimension_diagram = image
                    else:
                        image.image_type = "product"
                else:
                    # Small square images are likely accessories or icons
                    image.image_type = "accessory"
            
            # 4. Tall images (portrait orientation) - mounting/wiring diagrams or product photos
            elif aspect_ratio < 0.7:
                if image.height > 400:  # Very tall images are likely mounting/wiring diagrams
                    if "wiring" in description or "wire" in description:
                        image.image_type = "wiring"
                        extracted_data.wiring_diagrams.append(image)
                    elif "mount" in description or "installation" in description:
                        image.image_type = "mounting"
                    else:
                        image.image_type = "mounting"  # Default for tall technical drawings
                elif total_pixels > 30000:  # Large tall images could be product photos
                    image.image_type = "product"
                else:
                    image.image_type = "accessory"
            
            # 5. Moderately wide images (1.5 - 1.8 aspect ratio)
            elif 1.5 <= aspect_ratio < 1.8:
                if total_pixels > 40000:
                    image.image_type = "photometric"
                    extracted_data.beam_angle_diagrams.append(image)
                else:
                    image.image_type = "product"
            
            # 6. Default fallback - classify as product image
            else:
                if total_pixels > 20000:
                    image.image_type = "product"
                else:
                    image.image_type = "accessory"
        
        # Ensure we have at least one product image if we have images
        product_images = [img for img in extracted_data.images if img.image_type == "product"]
        if not product_images and extracted_data.images:
            # If no product images found, use the largest non-diagram image
            non_diagram_images = [
                img for img in extracted_data.images 
                if img.image_type not in ["dimension", "beam_pattern", "photometric", "mounting"]
            ]
            if non_diagram_images:
                largest = max(non_diagram_images, key=lambda img: img.width * img.height)
                largest.image_type = "product"
        
        # Log classification results for debugging
        print(f"[DEBUG] Image classification complete:")
        print(f"  Total images: {len(extracted_data.images)}")
        print(f"  Product images: {len([img for img in extracted_data.images if img.image_type == 'product'])}")
        print(f"  Beam/Photometric diagrams: {len(extracted_data.beam_angle_diagrams)}")
        print(f"  Dimension diagram: {'Yes' if extracted_data.dimension_diagram else 'No'}")
        print(f"  Mounting/Wiring diagrams: {len([img for img in extracted_data.images if img.image_type == 'mounting'])}")
        print(f"  Accessory images: {len([img for img in extracted_data.images if img.image_type == 'accessory'])}")
    
    def _generate_tagline(self, data: VendorSpecData) -> str:
        """Generate a marketing tagline for the product"""
        category = data.product_category.lower() if data.product_category else ""
        name = data.product_name.lower() if data.product_name else ""
        
        taglines = {
            "flood": "Powerful Illumination for Every Application",
            "street": "Illuminating Pathways with Precision & Efficiency",
            "high bay": "Industrial-Grade Performance, Exceptional Efficiency",
            "stadium": "Professional Lighting for Championship Performance",
            "area": "Brilliant Coverage for Wide Open Spaces",
            "wall pack": "Secure Illumination for Building Perimeters",
            "canopy": "Superior Lighting for Covered Areas",
            "panel": "Sleek Design with Superior Light Quality",
            "tube": "Efficient Retrofit Solution for Modern Spaces"
        }
        
        for key, tagline in taglines.items():
            if key in category or key in name:
                return tagline
        
        return "High Performance LED Lighting Solution"
    
    def _calculate_confidence(self, data: VendorSpecData) -> float:
        """Calculate confidence score based on extracted data completeness"""
        score = 0.0
        max_score = 10.0
        
        if data.product_name:
            score += 1.5
        if data.product_description:
            score += 1.0
        if len(data.features) >= 3:
            score += 1.0
        if len(data.applications) >= 2:
            score += 0.5
        if len(data.electrical_specs) >= 3:
            score += 1.5
        if len(data.optical_specs) >= 3:
            score += 1.5
        if len(data.physical_specs) >= 2:
            score += 1.0
        if len(data.environmental_specs) >= 2:
            score += 0.5
        if len(data.certifications) >= 2:
            score += 0.5
        if data.ordering_info or data.part_number_structure:
            score += 1.0
        
        return min(score / max_score, 1.0)


def process_vendor_spec(pdf_path: str, api_key: Optional[str] = None, provider: Optional[str] = None) -> VendorSpecData:
    """
    Convenience function to process a vendor spec sheet.
    
    Args:
        pdf_path: Path to the vendor PDF
        api_key: Optional API key (uses config if not provided)
        provider: Optional provider name ("groq", "gemini", "ollama", "openai")
    """
    processor = AIVisionProcessor(provider=provider, api_key=api_key)
    return processor.process_vendor_pdf(pdf_path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = process_vendor_spec(sys.argv[1])
        print(json.dumps(asdict(result), indent=2, default=str))
    else:
        print("Usage: python ai_vision_processor.py <vendor_spec.pdf>")
        print("\nSupported FREE AI providers:")
        print("  - Groq: Set GROQ_API_KEY (get free key at https://console.groq.com)")
        print("  - Gemini: Set GEMINI_API_KEY (get free key at https://aistudio.google.com)")
        print("  - Ollama: Install from https://ollama.ai (local, no key needed)")
