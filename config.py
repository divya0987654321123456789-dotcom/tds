"""
Configuration settings for AI-Powered TDS Spec Sheet Generator
Supports FREE AI alternatives: Groq, Google Gemini, Ollama (local)
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

# =============================================================================
# AI PROVIDER CONFIGURATION - FREE OPTIONS
# =============================================================================

# Primary AI Provider: "groq", "gemini", "ollama", "openai"
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")

# Groq API (FREE - Fast inference with Llama/Mixtral)
# Get free key: https://console.groq.com/keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")  # Free, powerful

# Google Gemini (FREE tier available)
# Get free key: https://aistudio.google.com/apikey
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")  # Free, supports vision

# Ollama (FREE - Local models, no API key needed)
# Install: https://ollama.ai
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")  # For text
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava")  # For images

# OpenAI (Paid - fallback option)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o")
AI_VISION_MODEL = os.getenv("AI_VISION_MODEL", "gpt-4o")

# =============================================================================
# PATHS
# =============================================================================

BASE_DIR = Path(__file__).parent
TEMPLATE_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
FONTS_DIR = BASE_DIR / "fonts"
ASSETS_DIR = BASE_DIR / "assets"
IMAGES_DIR = BASE_DIR / "images"  # Standard certification/warranty images
TEMP_DIR = BASE_DIR / "temp"
VENDOR_INPUT_DIR = BASE_DIR / "vendor_input"

# Ensure directories exist
for directory in [OUTPUT_DIR, TEMPLATE_DIR, FONTS_DIR, ASSETS_DIR, IMAGES_DIR, TEMP_DIR, VENDOR_INPUT_DIR]:
    directory.mkdir(exist_ok=True)

# =============================================================================
# COMPANY BRANDING - IKIO/KIO LED Lighting
# =============================================================================

COMPANY_CONFIG = {
    "name": "IKIO LED LIGHTING",
    "short_name": "IKIO",
    "tagline": "Illuminating Excellence",
    
    # Brand Colors (matching Exiona TDS template)
    "colors": {
        "primary": "#1E3A5F",           # Deep Navy Blue
        "secondary": "#4A90A4",         # Teal Blue
        "accent": "#F5A623",            # Orange accent
        "header_bg": "#1E3A5F",         # Header background
        "table_header": "#003366",      # Dark blue for table headers
        "table_alt_row": "#E8F4F8",     # Light blue alternating rows
        "text_dark": "#2C3E50",         # Dark text
        "text_light": "#7F8C8D",        # Light gray text
        "border": "#BDC3C7",            # Border color
        "white": "#FFFFFF",
        "light_bg": "#F8F9FA",
    },
    
    # Contact Information
    "website": "www.kioledlighting.com",
    "email": "info@kioledlighting.com",
    "phone": "+1 844-333-4548",
    "address": "Corporate Office",
    
    # Assets
    "logo_path": str(ASSETS_DIR / "logo.png"),
    "footer_logo_path": str(ASSETS_DIR / "footer-logo.png"),
    
    # Footer text
    "copyright_text": "© {year} IKO LED LIGHTING. All Rights Reserved.",
    "disclaimer": "Products and technologies in this document may be covered by one or more Patents Pending. The product images shown are for illustration purposes only and may not be an exact representation of the product. Specifications subject to change without notice."
}

# =============================================================================
# PDF TEMPLATE SETTINGS
# =============================================================================

PDF_SETTINGS = {
    "page_size": "LETTER",  # US Letter size
    "margin_top": 85,
    "margin_bottom": 55,
    "margin_left": 40,
    "margin_right": 40,
    "header_height": 75,
    "footer_height": 45
}

# =============================================================================
# SPECIFICATION CATEGORIES
# =============================================================================

SPEC_CATEGORIES = {
    "electrical": {
        "name": "Electrical Specifications",
        "fields": [
            "Power", "Voltage", "Power Factor", "Surge Protection",
            "THD", "Frequency", "Inrush Current", "Input Current"
        ]
    },
    "optical": {
        "name": "Lighting Performance",
        "fields": [
            "Lumens", "Efficacy", "Color Temperature (CCT)", "CRI",
            "Beam Angle", "Light Distribution", "Dimmable Light Control"
        ]
    },
    "environmental": {
        "name": "Environmental Ratings",
        "fields": [
            "Operating Temperature", "IP Rating", "IK Rating",
            "Humidity", "Ambient Temperature"
        ]
    },
    "physical": {
        "name": "Physical Specifications",
        "fields": [
            "Dimensions", "Weight", "Housing Material", "Lens Material",
            "Finish", "Color", "EPA"
        ]
    },
    "lifespan": {
        "name": "Lifespan & Warranty",
        "fields": [
            "Average Life (Hours)", "L70", "L80", "L90", "Warranty (Years)"
        ]
    },
    "components": {
        "name": "Components",
        "fields": [
            "LED Light Source", "Power Supply", "Driver", "LED Chip"
        ]
    }
}

# =============================================================================
# AI EXTRACTION PROMPTS
# =============================================================================

AI_PROMPTS = {
    "text_extraction": """You are an expert LED lighting engineer and technical specification analyst.
Analyze this LED lighting product specification text with deep technical understanding and extract ALL information comprehensively.

CRITICAL INSTRUCTIONS:
- Only extract ENGLISH text. Completely ignore and skip any non-English text including Chinese, Japanese, Korean, Arabic, or any other non-Latin script languages.
- Understand the engineering context - infer implicit specifications from explicit ones (e.g., if CCT is selectable, note that as a feature)
- Extract ALL technical details including ranges, options, and variants
- Understand the product category and application context
- Extract comprehensive feature lists - not just what's explicitly stated, but what can be inferred from specs

Return a comprehensive JSON object with ALL of the following fields:

1. product_info: {
     name: Clean product name (remove vendor codes/model numbers from display name)
     model: Model number(s) - capture ALL variants
     category: Product category (e.g., "Area Luminaire", "Flood Light", "High Bay")
     series: Product series if mentioned
     description: Comprehensive 2-3 sentence description highlighting key technical benefits
   }

2. features: List of 8-12 comprehensive features including:
   - Technical features (e.g., "High-Efficacy LED Technology", "Advanced Thermal Management")
   - Performance features (e.g., "Selectable CCT Options", "Dimmable Control")
   - Durability features (e.g., "IP65 Weatherproof Rating", "Corrosion-Resistant Housing")
   - Design features (e.g., "Optimal Light Distribution", "Modern Aesthetic Design")
   - Infer features from specifications (e.g., if CCT is selectable, add "CCT Selectable")

3. applications: List of 6-10 application areas (e.g., ["Parking Lots", "Street Lighting", "Loading Docks"])

4. electrical_specs: ALL electrical specifications with units:
   - Input Voltage (include full range, e.g., "100-277V AC")
   - Wattage (include ALL variants, e.g., "70W / 100W / 150W")
   - Power Factor (minimum value, e.g., "≥0.9")
   - THD (Total Harmonic Distortion, e.g., "<20%")
   - Frequency (e.g., "50/60 Hz")
   - Surge Protection (if available, e.g., "6kV")
   - Input Current (calculate if wattage and voltage provided)

5. optical_specs: ALL optical/lighting specifications with units:
   - Lumens (include ALL variants with units, e.g., "7,000 lm / 10,000 lm")
   - Efficacy (include ALL variants, e.g., "100 lm/W / 110 lm/W")
   - CCT (Color temperature options, e.g., "3000K / 4000K / 5000K" or "3000K-5000K Selectable")
   - CRI (Color Rendering Index, e.g., "≥80")
   - Beam Angle (e.g., "120°" or "Type III")
   - Light Distribution (e.g., "Type III", "Type V", "Asymmetric")
   - LED Source (LED chip type if mentioned)

6. physical_specs: ALL physical specifications:
   - Housing Material (e.g., "Die-Cast Aluminum")
   - Lens Material (e.g., "Polycarbonate" or "Tempered Glass")
   - Finish (e.g., "Bronze" or "Black Powder Coating")
   - Dimensions (Full dimensions L x W x H with units, e.g., "12.5\" x 8.5\" x 6.2\"")
   - Weight (Net weight with units, e.g., "8.5 lbs")
   - Mounting Type (e.g., "Pole Mount" or "Wall Mount / Ceiling Mount")
   - EPA (Effective Projected Area if available)

7. environmental_specs: ALL environmental specifications:
   - IP Rating (e.g., "IP65" or "IP66")
   - IK Rating (if available, e.g., "IK08")
   - Operating Temperature (Full range with units, e.g., "-40°F to 140°F")
   - Suitable Location (e.g., "Wet Location" or "Damp Location")

8. lifespan_specs: Lifespan and warranty information:
   - Lifespan (e.g., "50,000 hours" or "L70 @ 50,000 hours")
   - Warranty (e.g., "5 years" or "10 years")

9. certifications: Comprehensive list of ALL certifications:
   - Safety certifications (UL, ETL, CE, cETLus)
   - Energy certifications (DLC Premium, DLC Standard, Energy Star)
   - Environmental certifications (RoHS)
   - IP ratings if significant
   - Any other certifications mentioned

10. ordering_info: Part number structure, variants, options:
    - Part number format/pattern
    - All ordering codes and options
    - Variant descriptions

11. accessories: Both included and sold separately:
    - Name, description, part number for each accessory
    - Distinguish between included vs. sold separately

12. tables: Extract ALL table data preserving exact structure:
    - Headers
    - All rows
    - Table type (specifications, ordering, accessories, etc.)

ENGINEERING CONTEXT UNDERSTANDING:
- If specifications show ranges or multiple options, extract ALL of them
- Infer features from specifications (e.g., selectable CCT = "CCT Selectable" feature)
- Understand technical relationships (e.g., efficacy = lumens/wattage)
- Extract implicit information (e.g., if IP65 rated, suitable for wet locations)

Be extremely thorough - extract EVERY piece of ENGLISH text and data.
For tables, preserve the exact structure with headers and all rows.
For specifications with multiple values (like multiple wattages), capture ALL variants.
Skip any content that is not in English.

Return ONLY valid JSON, no markdown formatting.""",

    "vision_extraction": """You are an expert LED lighting engineer and technical specification analyst.
Analyze this LED lighting product specification sheet image with deep technical understanding and extract ALL information comprehensively.

CRITICAL INSTRUCTIONS:
- Only extract ENGLISH text. Completely ignore and skip any non-English text including Chinese, Japanese, Korean, Arabic, or any other non-Latin script languages.
- Understand the engineering context - infer implicit specifications from explicit ones (e.g., if CCT is selectable, note that as a feature)
- Extract ALL technical details including ranges, options, and variants
- Pay attention to diagrams, charts, and technical drawings - describe what they show
- Understand the product category and application context
- Extract comprehensive feature lists - not just what's explicitly stated, but what can be inferred from specs

Return a comprehensive JSON object with ALL of the following fields:

1. product_info: {
     name: Clean product name (remove vendor codes/model numbers from display name)
     model: Model number(s) - capture ALL variants
     category: Product category (e.g., "Area Luminaire", "Flood Light", "High Bay")
     series: Product series if mentioned
     description: Comprehensive 2-3 sentence description highlighting key technical benefits
   }

2. features: List of 8-12 comprehensive features including:
   - Technical features (e.g., "High-Efficacy LED Technology", "Advanced Thermal Management")
   - Performance features (e.g., "Selectable CCT Options", "Dimmable Control")
   - Durability features (e.g., "IP65 Weatherproof Rating", "Corrosion-Resistant Housing")
   - Design features (e.g., "Optimal Light Distribution", "Modern Aesthetic Design")
   - Infer features from specifications (e.g., if CCT is selectable, add "CCT Selectable")

3. applications: List of 6-10 application areas (e.g., ["Parking Lots", "Street Lighting", "Loading Docks"])

4. electrical_specs: ALL electrical specifications with units:
   - Input Voltage (include full range, e.g., "100-277V AC")
   - Wattage (include ALL variants, e.g., "70W / 100W / 150W")
   - Power Factor (minimum value, e.g., "≥0.9")
   - THD (Total Harmonic Distortion, e.g., "<20%")
   - Frequency (e.g., "50/60 Hz")
   - Surge Protection (if available, e.g., "6kV")
   - Input Current (calculate if wattage and voltage provided)

5. optical_specs: ALL optical/lighting specifications with units:
   - Lumens (include ALL variants with units, e.g., "7,000 lm / 10,000 lm")
   - Efficacy (include ALL variants, e.g., "100 lm/W / 110 lm/W")
   - CCT (Color temperature options, e.g., "3000K / 4000K / 5000K" or "3000K-5000K Selectable")
   - CRI (Color Rendering Index, e.g., "≥80")
   - Beam Angle (e.g., "120°" or "Type III")
   - Light Distribution (e.g., "Type III", "Type V", "Asymmetric")
   - LED Source (LED chip type if mentioned)

6. physical_specs: ALL physical specifications:
   - Housing Material (e.g., "Die-Cast Aluminum")
   - Lens Material (e.g., "Polycarbonate" or "Tempered Glass")
   - Finish (e.g., "Bronze" or "Black Powder Coating")
   - Dimensions (Full dimensions L x W x H with units, e.g., "12.5\" x 8.5\" x 6.2\"")
   - Weight (Net weight with units, e.g., "8.5 lbs")
   - Mounting Type (e.g., "Pole Mount" or "Wall Mount / Ceiling Mount")
   - EPA (Effective Projected Area if available)

7. environmental_specs: ALL environmental specifications:
   - IP Rating (e.g., "IP65" or "IP66")
   - IK Rating (if available, e.g., "IK08")
   - Operating Temperature (Full range with units, e.g., "-40°F to 140°F")
   - Suitable Location (e.g., "Wet Location" or "Damp Location")

8. lifespan_specs: Lifespan and warranty information:
   - Lifespan (e.g., "50,000 hours" or "L70 @ 50,000 hours")
   - Warranty (e.g., "5 years" or "10 years")

9. certifications: Comprehensive list of ALL certifications:
   - Safety certifications (UL, ETL, CE, cETLus)
   - Energy certifications (DLC Premium, DLC Standard, Energy Star)
   - Environmental certifications (RoHS)
   - IP ratings if significant
   - Any other certifications mentioned

10. ordering_info: Part number structure, variants, options:
    - Part number format/pattern
    - All ordering codes and options
    - Variant descriptions

11. accessories: Both included and sold separately:
    - Name, description, part number for each accessory
    - Distinguish between included vs. sold separately

12. diagrams: Descriptions of any diagrams visible:
    - Dimension diagrams: Describe what dimensions are shown
    - Beam patterns/photometric: Describe distribution patterns
    - Wiring diagrams: Describe wiring configurations
    - Mounting diagrams: Describe mounting options

13. tables: Extract ALL table data preserving exact structure:
    - Headers
    - All rows
    - Table type (specifications, ordering, accessories, etc.)

ENGINEERING CONTEXT UNDERSTANDING:
- If specifications show ranges or multiple options, extract ALL of them
- Infer features from specifications (e.g., selectable CCT = "CCT Selectable" feature)
- Understand technical relationships (e.g., efficacy = lumens/wattage)
- Extract implicit information (e.g., if IP65 rated, suitable for wet locations)

Be extremely thorough - extract EVERY piece of ENGLISH text and data visible.
For tables, preserve the exact structure with headers and all rows.
For specifications with multiple values (like multiple wattages), capture ALL variants.
Skip any content that is not in English.

Return ONLY valid JSON, no markdown formatting.""",

    "text_enhancement": """You are a technical writer for IKIO LED Lighting. 
Enhance and standardize the following product specifications for a Technical Data Sheet.

Rules:
1. Use professional, industry-standard terminology
2. Ensure consistent formatting and units
3. Generate a compelling product description (2-3 sentences)
4. Create a marketing tagline
5. Organize features in order of importance
6. Standardize all specification values to common formats

Return ONLY valid JSON, no markdown formatting."""
}

# =============================================================================
# TABLE STYLING CONFIGURATION
# =============================================================================

TABLE_STYLES = {
    "header": {
        "background": "#003366",
        "text_color": "#FFFFFF",
        "font_size": 10,
        "font_weight": "bold",
        "padding": 8
    },
    "row": {
        "background": "#FFFFFF",
        "alt_background": "#F0F8FF",
        "text_color": "#333333",
        "font_size": 9,
        "padding": 6
    },
    "border": {
        "color": "#CCCCCC",
        "width": 0.5
    }
}

# =============================================================================
# TDS SECTION ORDER
# =============================================================================

TDS_SECTION_ORDER = [
    "product_header",
    "product_description",
    "product_features",
    "application_areas",
    "dimensions_diagram",
    "mounting_options",
    "packaging_info",
    "technical_specifications",
    "ordering_information",
    "beam_angle_diagrams",
    "accessories",
    "wiring_diagrams",
    "photometric_data"
]


def get_active_provider_info():
    """Get information about the currently configured AI provider"""
    provider = AI_PROVIDER.lower()
    
    if provider == "groq":
        return {
            "name": "Groq",
            "configured": bool(GROQ_API_KEY),
            "model": GROQ_MODEL,
            "free": True,
            "vision": False
        }
    elif provider == "gemini":
        return {
            "name": "Google Gemini",
            "configured": bool(GEMINI_API_KEY),
            "model": GEMINI_MODEL,
            "free": True,
            "vision": True
        }
    elif provider == "ollama":
        return {
            "name": "Ollama (Local)",
            "configured": True,  # No API key needed
            "model": OLLAMA_MODEL,
            "free": True,
            "vision": True
        }
    elif provider == "openai":
        return {
            "name": "OpenAI",
            "configured": bool(OPENAI_API_KEY),
            "model": AI_MODEL,
            "free": False,
            "vision": True
        }
    else:
        return {
            "name": "Unknown",
            "configured": False,
            "model": "",
            "free": False,
            "vision": False
        }
