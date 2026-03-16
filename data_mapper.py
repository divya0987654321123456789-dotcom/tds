"""
Data Mapper - Transforms vendor spec data to IKIO company format
Standardizes specifications, generates ordering codes, and prepares data for TDS generation
"""
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

from ai_vision_processor import VendorSpecData, ExtractedTable, ExtractedImage
from image_asset_manager import get_asset_manager


@dataclass
class TDSSpecificationRow:
    """Single row in a specification table"""
    label: str
    values: List[str]  # Can have multiple values for variants (480W, 600W, etc.)


@dataclass
class TDSSpecificationTable:
    """Table of specifications for TDS"""
    title: str
    rows: List[List[str]] = field(default_factory=list)  # List of rows, each row is list of cell values
    headers: List[str] = field(default_factory=list)  # Column headers e.g., ["Parameter", "480W", "600W"]
    has_multiple_variants: bool = False


@dataclass
class TDSAccessory:
    """Accessory item for TDS"""
    name: str
    description: str = ""
    part_number: str = ""
    sku: str = ""
    code: str = ""
    download: str = ""
    image_path: str = ""
    image_data: Optional[bytes] = None


@dataclass
class TDSOrderingInfo:
    """Ordering information structure"""
    example_part_number: str = ""
    structure_description: str = ""
    components: List[Dict[str, Any]] = field(default_factory=list)
    # Each component: {"code": "IK", "name": "BRAND", "description": "IKIO", "options": [...]}


@dataclass 
class IKIOTDSData:
    """
    Complete data structure for generating IKIO TDS
    Uses IKIO template format with all specifications
    """
    # Header Information
    product_name: str = ""
    product_series: str = ""
    product_category: str = ""  # e.g., "LED DOWNLIGHT", "LED PANEL"
    document_title: str = "Technical Data Sheet"
    model_number: str = ""
    item_sku: str = ""
    project_name: str = ""
    catalog_number: str = ""
    fixture_schedule: str = ""
    issue_date: str = ""
    product_title: str = ""
    category_path: str = ""
    
    # Product Description Section
    product_description: str = ""
    
    # Electrical Specifications
    wattage: str = ""
    input_voltage: str = ""
    frequency: str = ""
    power_factor: str = ""
    thd: str = ""
    surge_protection: str = ""
    input_current: str = ""
    
    # Optical Specifications
    cct: str = ""  # Color Correlated Temperature
    cri: str = ""  # Color Rendering Index
    lumens: str = ""  # Luminous Flux
    efficacy: str = ""  # lm/W
    beam_angle: str = ""
    light_distribution: str = ""
    led_light_source: str = ""
    
    # Environmental Ratings
    ip_rating: str = ""
    ik_rating: str = ""
    lifespan: str = ""
    operating_temp: str = ""
    suitable_location: str = ""
    
    # Physical Specifications
    housing_material: str = ""
    lens_material: str = ""
    mounting_type: str = ""
    dimensions: str = ""
    cutout_size: str = ""
    product_weight: str = ""
    diffuser: str = ""
    power_supply: str = ""
    finish: str = ""
    epa: str = ""
    
    # Control
    dimming: str = ""
    
    # Warranty
    warranty: str = ""
    warranty_years: str = ""
    warranty_limitation: str = ""
    
    # Features Section (bullet points)
    features: List[str] = field(default_factory=list)

    # Qualifications (page 1)
    qualifications: str = ""
    
    # Application Areas Section
    applications: List[str] = field(default_factory=list)

    # Page-1 overview rows from the technical sheet form (Label/Value pairs)
    overview_rows: List[List[str]] = field(default_factory=list)

    # Editable section labels from the technical sheet form
    section_headings: Dict[str, str] = field(default_factory=dict)
    
    # Notes
    notes: List[str] = field(default_factory=list)
    
    # Technical Specification Tables
    spec_tables: List[TDSSpecificationTable] = field(default_factory=list)
    performance_table: Optional[TDSSpecificationTable] = None
    epa_table: Optional[TDSSpecificationTable] = None
    
    # Dimension Diagram
    dimension_diagram_path: str = ""
    dimension_diagram_data: Optional[bytes] = None

    # Dimension fields
    product_length: str = ""
    product_width: str = ""
    product_height: str = ""
    wire_length: str = ""
    net_weight: str = ""
    slip_fitter_length: str = ""
    slip_fitter_width: str = ""
    slip_fitter_height: str = ""
    slip_fitter_weight: str = ""
    
    # Mounting Options
    mounting_options: List[TDSAccessory] = field(default_factory=list)
    
    # Packaging Information
    packaging_weight: str = ""
    packaging_dimensions: str = ""
    box_weight: str = ""
    
    # Ordering Information (list of dicts)
    ordering_info: List[Dict[str, Any]] = field(default_factory=list)
    # Each: {"model": "", "wattage": "", "cct": "", "lumens": "", "sku": ""}
    
    # Ordering Structure (for part number breakdown)
    ordering_structure: TDSOrderingInfo = field(default_factory=TDSOrderingInfo)
    
    # Beam Angle Diagrams
    beam_angle_diagrams: List[Dict[str, Any]] = field(default_factory=list)
    photometrics_diagram_data: Optional[bytes] = None
    # Each: {"type": "Symmetrical 12°", "image_path": "", "image_data": bytes}
    
    # Accessories
    accessories: List[TDSAccessory] = field(default_factory=list)
    accessories_sold_separately: List[TDSAccessory] = field(default_factory=list)
    accessories_included: List[TDSAccessory] = field(default_factory=list)
    
    # Certifications (for display)
    certifications: List[str] = field(default_factory=list)
    certification_badges: List[bytes] = field(default_factory=list)
    
    # Wiring Diagrams
    wiring_diagrams: List[Dict[str, Any]] = field(default_factory=list)
    
    # Additional Images - storing image bytes and metadata from source PDF
    product_images: List[str] = field(default_factory=list)
    extracted_images: List[Dict[str, Any]] = field(default_factory=list)
    # Each: {"image_data": bytes, "image_type": str, "width": int, "height": int, "page_number": int}
    
    # Metadata
    generated_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    source_vendor: str = ""
    page_count: int = 2

    # Photometrics
    photometrics_note: str = ""

    # Optional canvas-based page layout overrides from the visual editor
    layout_overrides: Dict[str, Any] = field(default_factory=dict)


class VendorToIKIOMapper:
    """
    Maps vendor specification data to IKIO TDS format
    Handles standardization, unit conversion, and format matching
    """
    
    # Specification label standardization mapping
    SPEC_LABEL_MAP = {
        # Electrical
        "power": "Power",
        "wattage": "Power",
        "watts": "Power",
        "input voltage": "Voltage",
        "voltage": "Voltage",
        "voltage range": "Voltage",
        "power factor": "Power Factor",
        "pf": "Power Factor",
        "surge protection": "Surge Protection",
        "surge": "Surge Protection",
        "thd": "THD",
        "frequency": "Frequency",
        "inrush current": "Inrush Current",
        
        # Optical
        "lumens": "Lumens",
        "luminous flux": "Lumens",
        "light output": "Lumens",
        "efficacy": "Efficacy",
        "efficiency": "Efficacy",
        "lm/w": "Efficacy",
        "color temperature": "Color Temperature (CCT)",
        "cct": "Color Temperature (CCT)",
        "color temp": "Color Temperature (CCT)",
        "cri": "Color Rendering Index (CRI)",
        "color rendering": "Color Rendering Index (CRI)",
        "ra": "Color Rendering Index (CRI)",
        "beam angle": "Beam Angle",
        "beam": "Beam Angle",
        "distribution": "Light Distribution",
        "light distribution": "Light Distribution",
        "dimming": "Dimmable Light Control",
        "dimmable": "Dimmable Light Control",
        
        # Environmental
        "operating temperature": "Operating Temperature",
        "operating temp": "Operating Temperature",
        "ambient temperature": "Operating Temperature",
        "ip rating": "Ingress Protection Rating (IP)",
        "ip": "Ingress Protection Rating (IP)",
        "ingress protection": "Ingress Protection Rating (IP)",
        "ik rating": "Impact Protection Rating (IK)",
        "ik": "Impact Protection Rating (IK)",
        "impact rating": "Impact Protection Rating (IK)",
        
        # Physical
        "dimensions": "Dimensions",
        "size": "Dimensions",
        "weight": "Net Weight",
        "net weight": "Net Weight",
        "housing": "Housing",
        "housing material": "Housing",
        "body material": "Housing",
        "lens": "Lens",
        "lens material": "Lens",
        "finish": "Finish",
        "color": "Finish",
        "epa": "Effective Projected Area (EPA)",
        "effective projected area": "Effective Projected Area (EPA)",
        
        # Lifespan
        "lifespan": "Average Life (Hours)",
        "life": "Average Life (Hours)",
        "average life": "Average Life (Hours)",
        "l70": "Average Life (Hours)",
        "led life": "Average Life (Hours)",
        "warranty": "Warranty (Years)",
        "warranty years": "Warranty (Years)",
        
        # Components
        "led source": "LED Light Source",
        "led chip": "LED Light Source",
        "led": "LED Light Source",
        "light source": "LED Light Source",
        "driver": "Power Supply",
        "power supply": "Power Supply",
    }
    
    # Unit standardization
    UNIT_PATTERNS = {
        "temperature": (r"(-?\d+)\s*[°]?\s*[CF]?\s*(?:to|~|-)\s*(-?\d+)\s*[°]?\s*([CF])?", 
                       lambda m: f"{m.group(1)}°F ~ +{m.group(2)}°F" if 'F' in (m.group(3) or 'F') else f"{m.group(1)}°C to {m.group(2)}°C"),
        "watts": (r"(\d+(?:\.\d+)?)\s*[Ww](?:atts?)?", lambda m: f"{m.group(1)}W"),
        "lumens": (r"(\d+(?:,\d+)?)\s*[Ll][Mm]", lambda m: f"{m.group(1).replace(',','')}lm"),
        "efficacy": (r"(\d+(?:\.\d+)?)\s*[Ll][Mm]/[Ww]", lambda m: f"{m.group(1)}lm/W"),
    }
    
    def __init__(self):
        self.variant_columns = []
    
    def map_vendor_to_ikio(self, vendor_data: VendorSpecData) -> IKIOTDSData:
        """
        Transform vendor spec data to IKIO TDS format
        """
        tds = IKIOTDSData()
        
        # Combine all specs for easier lookup
        all_specs = {
            **vendor_data.electrical_specs,
            **vendor_data.optical_specs,
            **vendor_data.environmental_specs,
            **vendor_data.lifespan_specs,
            **vendor_data.component_specs,
            **vendor_data.physical_specs
        }
        
        # Map basic information
        tds.product_name = self._clean_product_name(vendor_data.product_name)
        tds.product_series = vendor_data.product_series
        tds.product_category = vendor_data.product_category or ""
        tds.product_description = self._format_description(vendor_data.product_description)
        tds.source_vendor = vendor_data.source_file
        
        # Map model numbers
        if vendor_data.model_numbers:
            tds.model_number = vendor_data.model_numbers[0]
            tds.catalog_number = vendor_data.model_numbers[0]
        
        # Map features (clean and standardize)
        tds.features = self._map_features(vendor_data.features)
        
        # Map applications
        tds.applications = self._map_applications(vendor_data.applications)
        
        # Detect variants (e.g., 480W and 600W)
        self.variant_columns = self._detect_variants(vendor_data)
        
        # ===== MAP INDIVIDUAL SPECIFICATION FIELDS =====
        # This is critical - extract individual fields so they can be rendered on page 1
        
        # Electrical Specifications
        tds.wattage = self._extract_spec_value(all_specs, ["Power", "Wattage", "Watts"])
        tds.input_voltage = self._extract_spec_value(all_specs, ["Voltage", "Input Voltage", "Voltage Range"])
        tds.input_current = self._extract_spec_value(all_specs, ["Current", "Input Current"])
        tds.frequency = self._extract_spec_value(all_specs, ["Frequency"])
        tds.power_factor = self._extract_spec_value(all_specs, ["Power Factor", "PF"])
        tds.thd = self._extract_spec_value(all_specs, ["THD", "Total Harmonic Distortion"])
        tds.surge_protection = self._extract_spec_value(all_specs, ["Surge Protection", "Surge"])
        
        # Optical Specifications
        tds.lumens = self._extract_spec_value(all_specs, ["Lumens", "Luminous Flux", "Light Output"])
        tds.efficacy = self._extract_spec_value(all_specs, ["Efficacy", "Efficiency", "lm/W"])
        tds.cct = self._extract_spec_value(all_specs, ["CCT", "Color Temperature", "Color Temp"])
        tds.cri = self._extract_spec_value(all_specs, ["CRI", "Color Rendering Index", "Ra"])
        tds.beam_angle = self._extract_spec_value(all_specs, ["Beam Angle", "Beam"])
        tds.light_distribution = self._extract_spec_value(all_specs, ["Light Distribution", "Distribution", "Distribution Type"])
        tds.led_light_source = self._extract_spec_value(all_specs, ["LED Source", "LED Chip", "LED", "Light Source"])
        
        # Environmental Ratings
        tds.ip_rating = self._extract_spec_value(all_specs, ["IP Rating", "IP", "Ingress Protection"])
        tds.ik_rating = self._extract_spec_value(all_specs, ["IK Rating", "IK", "Impact Rating"])
        tds.operating_temp = self._extract_spec_value(all_specs, ["Operating Temperature", "Operating Temp", "Ambient Temperature"])
        tds.suitable_location = self._extract_spec_value(all_specs, ["Suitable Location", "Location", "Application"])
        
        # Lifespan & Warranty
        tds.lifespan = self._extract_spec_value(all_specs, ["Lifespan", "Life", "Average Life", "L70", "LED Life"])
        tds.warranty = self._extract_spec_value(all_specs, ["Warranty", "Warranty Years"])
        tds.warranty_years = tds.warranty
        # Use getattr to safely access warranty_limitation (may not exist in VendorSpecData)
        warranty_limitation = getattr(vendor_data, 'warranty_limitation', '')
        if warranty_limitation:
            tds.warranty_limitation = warranty_limitation
        
        # Physical Specifications
        tds.housing_material = self._extract_spec_value(all_specs, ["Housing", "Housing Material", "Body Material"])
        tds.lens_material = self._extract_spec_value(all_specs, ["Lens", "Lens Material", "Cover Material"])
        tds.diffuser = self._extract_spec_value(all_specs, ["Diffuser"])
        tds.finish = self._extract_spec_value(all_specs, ["Finish", "Color"])
        tds.power_supply = self._extract_spec_value(all_specs, ["Power Supply", "Driver"])
        tds.mounting_type = self._extract_spec_value(all_specs, ["Mounting", "Mounting Type"])
        tds.epa = self._extract_spec_value(all_specs, ["EPA", "Effective Projected Area"])
        
        # Dimensions - improved extraction to handle various formats
        dimensions_str = self._extract_spec_value(all_specs, ["Dimensions", "Size", "Product Dimensions"])
        tds.dimensions = dimensions_str
        
        # Try to parse dimensions from string like "L x W x H" or "12.5\" x 8.5\" x 6.2\""
        if dimensions_str:
            import re
            # Pattern: numbers with units separated by x
            dim_pattern = r'(\d+(?:\.\d+)?)\s*["\']?\s*[xX×]\s*(\d+(?:\.\d+)?)\s*["\']?\s*[xX×]\s*(\d+(?:\.\d+)?)'
            match = re.search(dim_pattern, dimensions_str)
            if match:
                tds.product_length = match.group(1)
                tds.product_width = match.group(2)
                tds.product_height = match.group(3)
        
        # Individual dimension fields (if not parsed from combined string)
        if not tds.product_length:
            tds.product_length = self._extract_spec_value(all_specs, ["Length", "Product Length", "L"])
        if not tds.product_width:
            tds.product_width = self._extract_spec_value(all_specs, ["Width", "Product Width", "W"])
        if not tds.product_height:
            tds.product_height = self._extract_spec_value(all_specs, ["Height", "Product Height", "H"])
        
        tds.product_weight = self._extract_spec_value(all_specs, ["Weight", "Net Weight", "Product Weight"])
        tds.net_weight = tds.product_weight
        tds.cutout_size = self._extract_spec_value(all_specs, ["Cutout Size", "Cutout"])
        
        # Wire length
        tds.wire_length = self._extract_spec_value(all_specs, ["Wire Length", "Wire", "Cable Length"])
        
        # Control
        tds.dimming = self._extract_spec_value(all_specs, ["Dimming", "Dimmable", "Dimming Control"])
        
        # ===== INTELLIGENT INFERENCE - Fill missing data based on product type and industry standards =====
        self._intelligently_infer_missing_data(tds, vendor_data, all_specs)
        
        # Create specification tables
        tds.spec_tables = self._create_spec_tables(vendor_data)
        
        # Map dimension diagram
        if vendor_data.dimension_diagram:
            tds.dimension_diagram_data = vendor_data.dimension_diagram.image_data

        primary_photometric = next(
            (img for img in vendor_data.beam_angle_diagrams if getattr(img, "image_data", None)),
            None
        )
        if not primary_photometric:
            primary_photometric = next(
                (
                    img for img in vendor_data.images
                    if getattr(img, "image_data", None)
                    and getattr(img, "image_type", "") in {"photometric", "beam_pattern"}
                ),
                None
            )
        if primary_photometric:
            tds.photometrics_diagram_data = primary_photometric.image_data
        
        # Map packaging info
        tds.packaging_weight = vendor_data.packaging_info.get("weight", "")
        tds.packaging_dimensions = vendor_data.packaging_info.get("dimensions", "")
        tds.box_weight = vendor_data.packaging_info.get("box_weight", "")
        
        # Map mounting options
        tds.mounting_options = [
            TDSAccessory(
                name=opt.get("name", ""),
                description=opt.get("description", ""),
                image_path=opt.get("image", "")
            )
            for opt in vendor_data.mounting_options
        ]
        
        # Map ordering information
        tds.ordering_info = self._build_ordering_list(vendor_data)
        tds.ordering_structure = self._map_ordering_structure(vendor_data)
        
        # Map beam angle diagrams
        tds.beam_angle_diagrams = [
            {
                "type": f"Beam Angle {i+1}",
                "image_data": img.image_data
            }
            for i, img in enumerate(vendor_data.beam_angle_diagrams)
        ]

        tds.wiring_diagrams = [
            {
                "type": getattr(img, "image_type", "wiring"),
                "image_data": img.image_data,
            }
            for img in vendor_data.wiring_diagrams
            if getattr(img, "image_data", None)
        ]
        
        # Map accessories
        tds.accessories_sold_separately = [
            TDSAccessory(
                name=acc.get("name", ""),
                description=acc.get("description", "")
            )
            for acc in vendor_data.accessories_sold_separately
        ]
        
        tds.accessories_included = [
            TDSAccessory(
                name=acc.get("name", ""),
                description=acc.get("description", "")
            )
            for acc in vendor_data.accessories_included
        ]
        
        # Combine accessories for rendering
        tds.accessories = tds.accessories_sold_separately + tds.accessories_included
        
        # Map certifications
        tds.certifications = vendor_data.certifications
        
        # ALWAYS use standard certification badges from images folder (never use extracted badges)
        asset_manager = get_asset_manager()
        tds.certification_badges = []  # Start fresh with standard badges only
        
        # Get certification badges from standard images based on extracted certifications
        if vendor_data.certifications:
            standard_badges = asset_manager.get_certification_badges(vendor_data.certifications)
            if standard_badges:
                # Resize badges to fit TDS template (max 200x200)
                tds.certification_badges.extend([
                    asset_manager.resize_image(badge, max_width=200, max_height=200)
                    for badge in standard_badges
                ])
        
        # Also check IP rating for IP65 badge
        ip_rating = tds.ip_rating or self._extract_spec_value(all_specs, ["IP Rating", "IP"])
        if ip_rating:
            # Extract IP number (e.g., "IP65" -> "65", "65" -> "65")
            import re
            ip_match = re.search(r'(\d+)', str(ip_rating))
            if ip_match:
                ip_num = ip_match.group(1)
                if ip_num in ["65", "66", "67", "68"]:  # Common IP ratings
                    ip_badge = asset_manager.get_image_by_name("IP65")
                    if ip_badge and ip_badge not in tds.certification_badges:
                        tds.certification_badges.append(asset_manager.resize_image(ip_badge, max_width=200, max_height=200))
        
        # Get warranty badge if warranty info is available
        warranty_years = None
        warranty_str = tds.warranty or tds.warranty_years or ""
        if not warranty_str and vendor_data.lifespan_specs:
            warranty_str = vendor_data.lifespan_specs.get("Warranty", "")
        
        # Extract years from warranty string (e.g., "5 years", "5-year", "5yr", "5")
        import re
        if warranty_str:
            warranty_match = re.search(r'(\d+)\s*(?:year|yr|y)', str(warranty_str).lower())
            if warranty_match:
                warranty_years = int(warranty_match.group(1))
            else:
                # Try to extract just a number
                num_match = re.search(r'(\d+)', str(warranty_str))
                if num_match:
                    warranty_years = int(num_match.group(1))
        
        if warranty_years:
            warranty_badge = asset_manager.get_warranty_image(warranty_years)
            if warranty_badge:
                warranty_resized = asset_manager.resize_image(warranty_badge, max_width=200, max_height=200)
                # Check if already added (compare by checking if we have warranty badges)
                has_warranty = any('warranty' in str(b).lower() for b in tds.certification_badges[:10])  # Rough check
                if not has_warranty:
                    tds.certification_badges.append(warranty_resized)
        
        # Keep max 4 badges (prioritize certifications, then warranty)
        tds.certification_badges = tds.certification_badges[:4]
        
        # IMPORTANT: NEVER use vendor certification badges/icons - only use standard badges from images folder
        # Only extract product images, dimension diagrams, and technical diagrams - NOT certification badges
        # Filter out small icons and badges (these are replaced by standard badges from images folder)
        
        # #region agent log
        import json as _json_log
        print(f"[DEBUG] data_mapper: Received {len(vendor_data.images)} images from vendor_data")
        print(f"[DEBUG] data_mapper: Filtering out vendor badges/icons - using ONLY standard badges from images folder")
        try:
            with open(r"c:\Users\IKIO\Desktop\TDS-GENERATOR-13-NOV-2025\mycode\output\debug.log", "a") as _f:
                _f.write(_json_log.dumps({"location":"data_mapper.py:map_vendor_to_ikio:images_input","message":"Input images from vendor data","data":{"total_vendor_images":len(vendor_data.images),"images_sizes":[(img.width,img.height) for img in vendor_data.images[:10]]},"hypothesisId":"H4","sessionId":"debug-session","timestamp":__import__('time').time()*1000})+"\n")
        except Exception as _e:
            print(f"[DEBUG] Log write failed: {_e}")
        # #endregion
        
        # Keep technical diagrams even when they are smaller than product hero shots.
        MIN_IMAGE_SIZE = 120
        TECHNICAL_IMAGE_TYPES = {"dimension", "photometric", "beam_pattern", "wiring", "mounting"}

        tds.extracted_images = [
            {
                "image_data": img.image_data,
                "image_type": img.image_type,
                "width": img.width,
                "height": img.height,
                "page_number": img.page_number,
                "description": img.description
            }
            for img in vendor_data.images
            if (
                getattr(img, "image_data", None)
                and (
                    img.image_type in TECHNICAL_IMAGE_TYPES
                    or img.width >= MIN_IMAGE_SIZE
                    or img.height >= MIN_IMAGE_SIZE
                    or (img.width * img.height) >= 12000
                )
                and not (
                    img.image_type not in TECHNICAL_IMAGE_TYPES
                    and img.width < 210
                    and img.height < 210
                    and 0.78 <= (img.width / max(img.height, 1)) <= 1.32
                )
            )
        ]
        
        print(f"[DEBUG] data_mapper: After filtering badges/icons: {len(tds.extracted_images)} useful images (product photos, diagrams)")
        
        # #region agent log
        print(f"[DEBUG] data_mapper: After filtering (>=100x100): {len(tds.extracted_images)} images mapped")
        try:
            with open(r"c:\Users\IKIO\Desktop\TDS-GENERATOR-13-NOV-2025\mycode\output\debug.log", "a") as _f:
                _f.write(_json_log.dumps({"location":"data_mapper.py:map_vendor_to_ikio:images_output","message":"Mapped images after filtering","data":{"mapped_images_count":len(tds.extracted_images),"filtered_out":len(vendor_data.images)-len(tds.extracted_images)},"hypothesisId":"H2","sessionId":"debug-session","timestamp":__import__('time').time()*1000})+"\n")
        except Exception as _e:
            print(f"[DEBUG] Log write failed: {_e}")
        # #endregion
        
        # Determine page count
        tds.page_count = self._estimate_page_count(tds)
        
        return tds
    
    def _extract_spec_value(self, specs_dict: Dict[str, Any], label_variations: List[str]) -> str:
        """
        Extract a spec value from the specs dictionary trying multiple label variations.
        Handles both simple string values and dict values (for variants).
        Returns first matching value or empty string (never "Not specified").
        """
        for label in label_variations:
            # Try exact match (case-insensitive)
            for key, value in specs_dict.items():
                if key.lower().strip() == label.lower().strip():
                    if isinstance(value, dict):
                        # For variant specs, join all values or return first
                        values = [str(v) for v in value.values() if v and str(v).lower() not in ["not specified", "n/a", "na", "-", ""]]
                        if len(values) == 1:
                            return values[0]
                        elif len(values) > 1:
                            # Multiple variants - return range or list
                            return " / ".join(values)
                    result = str(value) if value else ""
                    # Remove "Not specified" and similar placeholders
                    if result.lower() in ["not specified", "n/a", "na", "-", "none", ""]:
                        return ""
                    return result
            
            # Try partial match
            for key, value in specs_dict.items():
                if label.lower() in key.lower() or key.lower() in label.lower():
                    if isinstance(value, dict):
                        values = [str(v) for v in value.values() if v and str(v).lower() not in ["not specified", "n/a", "na", "-", ""]]
                        if len(values) == 1:
                            return values[0]
                        elif len(values) > 1:
                            return " / ".join(values)
                    result = str(value) if value else ""
                    # Remove "Not specified" and similar placeholders
                    if result.lower() in ["not specified", "n/a", "na", "-", "none", ""]:
                        return ""
                    return result
        
        return ""
    
    def _intelligently_infer_missing_data(self, tds: IKIOTDSData, vendor_data: VendorSpecData, all_specs: Dict[str, Any]):
        """
        Intelligently infer missing specifications based on product type, category, and LED lighting industry standards.
        This makes the TDS smarter and more complete - not just copying vendor data.
        """
        product_category_lower = (tds.product_category or "").lower()
        product_name_lower = (tds.product_name or "").lower()
        
        # Infer IP rating for outdoor products
        if not tds.ip_rating:
            if any(word in product_category_lower or word in product_name_lower 
                   for word in ["outdoor", "area", "street", "flood", "wall pack", "canopy"]):
                tds.ip_rating = "IP65"  # Standard for outdoor LED products
                print("[INFERENCE] Inferred IP65 rating for outdoor product")
        
        # Infer power factor if missing (standard for quality LED products)
        if not tds.power_factor:
            tds.power_factor = "≥0.9"
            print("[INFERENCE] Inferred power factor ≥0.9")
        
        # Infer THD if missing (standard for quality LED drivers)
        if not tds.thd:
            tds.thd = "<20%"
            print("[INFERENCE] Inferred THD <20%")
        
        # Infer CRI if missing (standard for quality LED products)
        if not tds.cri:
            tds.cri = "≥80"
            print("[INFERENCE] Inferred CRI ≥80")
        
        # Infer lifespan if missing (standard for modern LED products)
        if not tds.lifespan:
            tds.lifespan = "50,000 hours"
            print("[INFERENCE] Inferred lifespan 50,000 hours")
        
        # Infer warranty if missing (industry standard)
        if not tds.warranty and not tds.warranty_years:
            tds.warranty = "5 years"
            tds.warranty_years = "5 years"
            print("[INFERENCE] Inferred 5-year warranty")
        
        # Infer housing material for outdoor products
        if not tds.housing_material:
            if any(word in product_category_lower or word in product_name_lower 
                   for word in ["outdoor", "area", "street", "flood", "wall pack"]):
                tds.housing_material = "Die-Cast Aluminum"
                print("[INFERENCE] Inferred Die-Cast Aluminum housing for outdoor product")
            else:
                tds.housing_material = "Aluminum"
                print("[INFERENCE] Inferred Aluminum housing")
        
        # Infer lens material for outdoor products
        if not tds.lens_material:
            if any(word in product_category_lower or word in product_name_lower 
                   for word in ["outdoor", "area", "street", "flood"]):
                tds.lens_material = "Polycarbonate"
                print("[INFERENCE] Inferred Polycarbonate lens for outdoor product")
        
        # Infer suitable location based on IP rating
        if not tds.suitable_location:
            if tds.ip_rating and ("65" in str(tds.ip_rating) or "66" in str(tds.ip_rating) or 
                                  "67" in str(tds.ip_rating) or "68" in str(tds.ip_rating)):
                tds.suitable_location = "Wet Location"
                print("[INFERENCE] Inferred Wet Location based on IP rating")
            elif tds.ip_rating and ("54" in str(tds.ip_rating) or "44" in str(tds.ip_rating)):
                tds.suitable_location = "Damp Location"
                print("[INFERENCE] Inferred Damp Location based on IP rating")
        
        # Infer applications based on product category
        if not tds.applications or len(tds.applications) < 3:
            inferred_apps = []
            if "area" in product_category_lower or "area" in product_name_lower:
                inferred_apps.extend(["Parking Lots", "Loading Docks", "Perimeter Security"])
            if "street" in product_category_lower or "street" in product_name_lower:
                inferred_apps.extend(["Street Lighting", "Roadways", "Highways"])
            if "flood" in product_category_lower or "flood" in product_name_lower:
                inferred_apps.extend(["Building Facades", "Landscape Lighting", "Signage"])
            if "downlight" in product_category_lower or "recessed" in product_category_lower:
                inferred_apps.extend(["Residential", "Commercial", "Institutional"])
            if "high bay" in product_category_lower:
                inferred_apps.extend(["Warehouses", "Manufacturing", "Gymnasiums"])
            
            if inferred_apps:
                # Add inferred apps if not already present
                existing_apps_lower = [a.lower() for a in tds.applications]
                for app in inferred_apps:
                    if app.lower() not in existing_apps_lower:
                        tds.applications.append(app)
                print(f"[INFERENCE] Inferred applications: {inferred_apps}")
        
        # Infer features based on specifications
        existing_features_lower = [f.lower() for f in tds.features]
        
        # If CCT has multiple values or is selectable, add "CCT Selectable" feature
        if tds.cct and ("/" in tds.cct or "selectable" in tds.cct.lower() or "-" in tds.cct):
            if "cct selectable" not in existing_features_lower and "selectable cct" not in existing_features_lower:
                tds.features.append("CCT Selectable")
                print("[INFERENCE] Added 'CCT Selectable' feature based on CCT specification")
        
        # If dimming mentioned, add "Dimmable Control" feature
        if tds.dimming and tds.dimming.lower() not in ["", "no", "none"]:
            if "dimmable" not in existing_features_lower and "dimming" not in existing_features_lower:
                tds.features.append("Dimmable Control")
                print("[INFERENCE] Added 'Dimmable Control' feature")
        
        # If IP65 or higher, add "Weatherproof" feature
        if tds.ip_rating and ("65" in str(tds.ip_rating) or "66" in str(tds.ip_rating) or 
                              "67" in str(tds.ip_rating) or "68" in str(tds.ip_rating)):
            if "weatherproof" not in existing_features_lower and "weather" not in existing_features_lower:
                tds.features.append("Weatherproof Construction")
                print("[INFERENCE] Added 'Weatherproof Construction' feature based on IP rating")
        
        # If high efficacy, add "Energy Efficient" feature
        if tds.efficacy:
            try:
                # Extract efficacy number
                import re
                eff_match = re.search(r'(\d+)', str(tds.efficacy))
                if eff_match:
                    eff_value = int(eff_match.group(1))
                    if eff_value >= 100:
                        if "energy efficient" not in existing_features_lower and "high efficacy" not in existing_features_lower:
                            tds.features.append("High-Efficacy LED Technology")
                            print("[INFERENCE] Added 'High-Efficacy LED Technology' feature")
            except:
                pass
        
        # Infer certifications based on product specifications
        if vendor_data.certifications:
            existing_certs_lower = [c.lower() for c in tds.certifications]
            
            # If IP65 outdoor product, likely has UL or ETL
            if tds.ip_rating and "65" in str(tds.ip_rating):
                if not any("ul" in c.lower() for c in tds.certifications):
                    if not any("etl" in c.lower() for c in tds.certifications):
                        # Don't add if not in vendor data - but AI enhancer will infer this
                        pass
            
            # If high efficacy, likely has DLC
            if tds.efficacy:
                try:
                    import re
                    eff_match = re.search(r'(\d+)', str(tds.efficacy))
                    if eff_match:
                        eff_value = int(eff_match.group(1))
                        if eff_value >= 100:
                            if not any("dlc" in c.lower() for c in tds.certifications):
                                # AI enhancer will infer DLC Premium/Standard
                                pass
                except:
                    pass
    
    def _clean_product_name(self, name: str) -> str:
        """Clean and format product name"""
        if not name:
            return "LED Lighting Product"
        
        # Remove extra whitespace
        name = " ".join(name.split())
        
        # Ensure proper capitalization
        words = name.split()
        formatted = []
        for word in words:
            if word.upper() in ["LED", "IP", "IK", "DMX", "UV", "RGB"]:
                formatted.append(word.upper())
            elif word.lower() in ["and", "or", "for", "with", "the"]:
                formatted.append(word.lower())
            else:
                formatted.append(word.title())
        
        return " ".join(formatted)
    
    def _format_description(self, description: str) -> str:
        """Format product description"""
        if not description:
            return ""
        
        # Clean up whitespace
        description = " ".join(description.split())
        
        # Ensure it ends with a period
        if description and not description.endswith('.'):
            description += '.'
        
        return description
    
    def _map_features(self, features: List[str]) -> List[str]:
        """Clean and standardize features list"""
        cleaned = []
        for feature in features:
            if not feature:
                continue
            
            # Clean whitespace
            feature = " ".join(feature.split())
            
            # Remove bullet points or dashes at start
            feature = re.sub(r'^[\-•●○◦]\s*', '', feature)
            
            # Ensure proper sentence format
            if feature and not feature[0].isupper():
                feature = feature[0].upper() + feature[1:]
            
            if feature and feature not in cleaned:
                cleaned.append(feature)
        
        return cleaned[:10]  # Limit to 10 features
    
    def _map_applications(self, applications: List[str]) -> List[str]:
        """Clean and standardize applications list"""
        cleaned = []
        for app in applications:
            if not app:
                continue
            
            # Clean and format
            app = " ".join(app.split())
            app = re.sub(r'^[\-•●○◦]\s*', '', app)
            
            if app and app not in cleaned:
                cleaned.append(app)
        
        return cleaned
    
    def _detect_variants(self, vendor_data: VendorSpecData) -> List[str]:
        """Detect product variants (e.g., different wattages)"""
        variants = []
        
        # Check for power variants in electrical specs
        power_spec = vendor_data.electrical_specs.get("Power", "")
        if isinstance(power_spec, dict):
            variants = list(power_spec.keys())
        elif isinstance(power_spec, str):
            # Look for multiple wattages like "480W / 600W"
            wattages = re.findall(r'(\d+)\s*W', power_spec)
            if len(wattages) > 1:
                variants = [f"{w}W" for w in wattages]
        
        # Also check model numbers
        if not variants and vendor_data.model_numbers:
            # Try to extract variants from model numbers
            for model in vendor_data.model_numbers:
                match = re.search(r'(\d+)\s*W', model, re.IGNORECASE)
                if match:
                    variant = f"{match.group(1)}W"
                    if variant not in variants:
                        variants.append(variant)
        
        return variants
    
    def _create_spec_tables(self, vendor_data: VendorSpecData) -> List[TDSSpecificationTable]:
        """Create standardized specification tables"""
        tables = []
        
        # Main Technical Specifications Table
        main_specs = []
        all_specs = {
            **vendor_data.electrical_specs,
            **vendor_data.optical_specs,
            **vendor_data.environmental_specs,
            **vendor_data.lifespan_specs,
            **vendor_data.component_specs,
            **vendor_data.physical_specs
        }
        
        # Define the order of specifications (matching Exiona template)
        spec_order = [
            "Power", "Voltage", "Power Factor", "Surge Protection",
            "Lumens", "Efficacy", "Color Temperature (CCT)", 
            "Color Rendering Index (CRI)", "Beam Angle", "Dimmable Light Control",
            "Operating Temperature", "Ingress Protection Rating (IP)",
            "Impact Protection Rating (IK)", "Average Life (Hours)",
            "Warranty (Years)", "LED Light Source", "Housing", "Lens",
            "Finish", "Power Supply", "Effective Projected Area (EPA)"
        ]
        
        for spec_key in spec_order:
            # Find matching spec in extracted data
            value = None
            for vendor_key, vendor_value in all_specs.items():
                standardized = self._standardize_label(vendor_key)
                if standardized == spec_key:
                    value = vendor_value
                    break
            
            if value:
                if isinstance(value, dict) and self.variant_columns:
                    # Multiple variants - create row as list of strings
                    row = [spec_key] + [str(value.get(v, "")) for v in self.variant_columns]
                    main_specs.append(row)
                else:
                    # Single value - create row as [label, value]
                    row = [spec_key, self._format_spec_value(spec_key, str(value))]
                    main_specs.append(row)
        
        if main_specs:
            # Build headers
            if len(self.variant_columns) > 1:
                headers = ["Parameter"] + list(self.variant_columns)
            else:
                headers = ["Parameter", "Value"]
            
            tables.append(TDSSpecificationTable(
                title="Technical Specifications",
                rows=main_specs,
                headers=headers,
                has_multiple_variants=len(self.variant_columns) > 1
            ))
        
        return tables
    
    def _standardize_label(self, label: str) -> str:
        """Standardize a specification label to IKIO format"""
        label_lower = label.lower().strip()
        
        # Direct mapping
        if label_lower in self.SPEC_LABEL_MAP:
            return self.SPEC_LABEL_MAP[label_lower]
        
        # Partial matching
        for key, mapped in self.SPEC_LABEL_MAP.items():
            if key in label_lower or label_lower in key:
                return mapped
        
        # Return original with title case if no match
        return label.title()
    
    def _format_spec_value(self, spec_type: str, value: str) -> str:
        """Format specification value with proper units"""
        if not value or value.lower() in ["n/a", "na", "-", ""]:
            return ""
        
        value = str(value).strip()
        
        # Handle specific formatting
        if "temperature" in spec_type.lower():
            # Ensure proper temperature format
            if "°" not in value:
                value = value.replace("C", "°C").replace("F", "°F")
        
        elif "rating" in spec_type.lower():
            # Ensure IP/IK format
            if spec_type.lower().startswith("ip") and not value.upper().startswith("IP"):
                value = f"IP{value}"
            elif spec_type.lower().startswith("ik") and not value.upper().startswith("IK"):
                value = f"IK{value}"
        
        return value
    
    def _build_ordering_list(self, vendor_data: VendorSpecData) -> List[Dict[str, Any]]:
        """Build ordering info list from vendor data"""
        ordering_list = []
        
        # Try to extract variants from electrical specs
        power_variants = vendor_data.electrical_specs.get("Power", {})
        if isinstance(power_variants, dict):
            for variant, wattage in power_variants.items():
                lumens_variants = vendor_data.optical_specs.get("Lumens", {})
                lumens = lumens_variants.get(variant, "") if isinstance(lumens_variants, dict) else ""
                
                ordering_list.append({
                    "model": f"{vendor_data.product_name} {variant}",
                    "wattage": wattage,
                    "cct": vendor_data.optical_specs.get("CCT", ""),
                    "lumens": lumens,
                    "sku": f"IKIO-{variant}"
                })
        
        # If no variants found, create single entry
        if not ordering_list and vendor_data.product_name:
            wattage = vendor_data.electrical_specs.get("Power", "")
            if isinstance(wattage, dict):
                wattage = next(iter(wattage.values()), "")
            ordering_list.append({
                "model": vendor_data.product_name,
                "wattage": str(wattage),
                "cct": vendor_data.optical_specs.get("CCT", ""),
                "lumens": vendor_data.optical_specs.get("Lumens", ""),
                "sku": ""
            })
        
        return ordering_list
    
    def _map_ordering_structure(self, vendor_data: VendorSpecData) -> TDSOrderingInfo:
        """Map ordering structure to TDS format"""
        ordering = TDSOrderingInfo()
        
        if vendor_data.ordering_info:
            ordering.example_part_number = vendor_data.ordering_info.get("example", "")
            ordering.structure_description = vendor_data.part_number_structure
            
            # Parse components if available
            if "components" in vendor_data.ordering_info:
                ordering.components = vendor_data.ordering_info["components"]
        
        return ordering
    
    def _estimate_page_count(self, tds: IKIOTDSData) -> int:
        """Estimate number of pages needed for the TDS"""
        # Add pages based on content
        content_score: float = 0.0
        content_score += len(tds.features) * 0.1
        content_score += len(tds.applications) * 0.05
        content_score += sum(len(t.rows) for t in tds.spec_tables) * 0.05
        content_score += len(tds.beam_angle_diagrams) * 0.15
        content_score += len(tds.accessories_sold_separately) * 0.1
        content_score += 0.3 if tds.dimension_diagram_data else 0.0
        content_score += 0.2 if tds.ordering_info else 0.0
        
        return max(2, int(content_score) + 1)


def map_vendor_to_tds(vendor_data: VendorSpecData) -> IKIOTDSData:
    """Convenience function to map vendor data to IKIO TDS format"""
    mapper = VendorToIKIOMapper()
    return mapper.map_vendor_to_ikio(vendor_data)


if __name__ == "__main__":
    # Test with sample data
    from ai_vision_processor import VendorSpecData
    
    test_data = VendorSpecData(
        product_name="Exiona Stadium Flood Light",
        product_description="High power flood light for professional applications",
        features=["High efficacy", "DMX dimmable", "IP66 rated"],
        applications=["Soccer Fields", "Stadiums", "Tennis Courts"],
        electrical_specs={"Power": {"480W": "480W", "600W": "600W"}, "Voltage": "120-277V AC"},
        optical_specs={"Lumens": {"480W": "62400lm", "600W": "78000lm"}, "Efficacy": "130lm/W"}
    )
    
    result = map_vendor_to_tds(test_data)
    print(asdict(result))

