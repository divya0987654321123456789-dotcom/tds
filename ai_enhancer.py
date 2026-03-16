"""
AI Content Enhancer for IKIO TDS Generator
==========================================
Takes raw extracted vendor data and uses AI (Groq/Gemini) to:
  - Rewrite descriptions professionally
  - Fill in missing fields using inference
  - Standardize spec values to IKIO format
  - Generate compelling features and applications
  - Produce marketing-ready content for the spec sheet
"""
import json
import re
from typing import Optional
from dataclasses import asdict
from rich.console import Console

from ai_client import get_ai_client
from ai_vision_processor import VendorSpecData

console = Console()

# ─────────────────────────────────────────────────────────────────────────────
# Master enhancement prompt
# ─────────────────────────────────────────────────────────────────────────────
ENHANCEMENT_PROMPT = """You are a senior technical writer and LED lighting engineering expert at IKIO LED Lighting, a professional LED lighting company.
Your job is to take raw, messy vendor specification data and intelligently transform it into polished, comprehensive, unique professional content
for IKIO's Technical Data Sheet (TDS) template.

IKIO's brand voice: professional, concise, technically precise, confidence-inspiring, engineering-focused, unique and distinctive.

CRITICAL INSTRUCTIONS - BE INTELLIGENT AND CREATIVE:
- DO NOT just copy vendor data - intelligently enhance, infer, and generate professional content
- Deeply understand the engineering context and technical specifications
- INFER missing specifications based on product type, category, and LED lighting industry standards
- INFER implicit features from specifications (e.g., selectable CCT → "CCT Selectable" feature, IP65 → "Weatherproof" feature)
- INFER missing data using industry knowledge (e.g., if no CRI mentioned but high-end product → infer CRI ≥80)
- INFER applications based on product type and specifications
- INFER certifications based on product specifications (e.g., outdoor IP65 → likely UL/ETL, high efficacy → likely DLC)
- Write unique, comprehensive content that adds value beyond what vendor provided
- Make content distinctive and professional - not just a copy of vendor specsheet
- Fill in missing fields intelligently based on product category and industry standards
- Enhance descriptions to be more compelling and professional

Given the raw vendor data below, return a single JSON object with ALL of the following fields populated.
Use the vendor data as your primary source. Where data is missing or unclear, infer reasonable values
based on the product type, LED lighting industry standards, and engineering best practices.

RULES:
1. product_name: Clean, professional product name (e.g. "Areon Area Luminaire" not "AREON AL BRONZE 70W/100W/150W MV TDS")
   - Remove vendor codes, model numbers, and technical suffixes from the display name
   - Keep it concise but descriptive

2. product_category: IKIO category path (e.g. "OUTDOOR LIGHTS | AREA LUMINAIRES")
   - Use proper IKIO category structure
   - Common categories: "OUTDOOR LIGHTS | AREA LUMINAIRES", "INDOOR LIGHTS | HIGH BAY", "OUTDOOR LIGHTS | STREET LIGHTS", etc.

3. product_description: Write 3-4 comprehensive sentences. Professional, marketing-ready, engineering-focused.
   - First sentence: Main application and key benefit
   - Second sentence: Technical highlights (efficacy, durability, performance)
   - Third sentence: Design features and materials
   - Fourth sentence (optional): Installation or application benefits
   - Example: "The [Product Name] delivers exceptional illumination for large outdoor areas with superior energy efficiency. 
     Featuring high-efficacy LED technology and robust IP65-rated construction, this luminaire ensures reliable performance 
     in demanding environments. The precision-engineered housing and advanced thermal management system provide extended lifespan 
     and consistent light output. Ideal for parking lots, loading docks, and perimeter security applications."

4. tagline: One punchy line (max 10 words). E.g. "Brilliant Coverage for Wide Open Spaces" or "Industrial-Grade Performance, Exceptional Efficiency"

5. features: List of 8-12 comprehensive bullet points. Start each with a strong verb or noun. No duplicates. English only.
   - Include technical features (e.g., "High-Efficacy LED Technology", "Advanced Thermal Management")
   - Include performance features (e.g., "Selectable CCT Options", "Dimmable Control")
   - Include durability features (e.g., "IP65 Weatherproof Rating", "Corrosion-Resistant Housing")
   - Include design features (e.g., "Sleek Modern Design", "Optimal Light Distribution")
   - Be specific and technical

6. applications: List of 6-10 application areas. Short noun phrases. E.g. ["Parking Lots", "Street Lighting", "Loading Docks", "Perimeter Security"]

7. electrical_specs: Dict of standardized electrical specs. Keys must use IKIO standard labels:
   - "Input Voltage": Include full range (e.g., "100-277V AC" or "120V / 277V")
   - "Wattage": Include all variants (e.g., "70W / 100W / 150W")
   - "Power Factor": Minimum value (e.g., "≥0.9" or "0.95")
   - "THD": Total Harmonic Distortion (e.g., "<20%" or "≤15%")
   - "Frequency": Operating frequency (e.g., "50/60 Hz")
   - "Surge Protection": If available (e.g., "6kV" or "10kV")
   - "Input Current": Calculate if wattage and voltage provided

8. optical_specs: Dict with keys:
   - "Lumens": Include all variants with units (e.g., "7,000 lm / 10,000 lm / 15,000 lm")
   - "Efficacy": Include all variants (e.g., "100 lm/W / 110 lm/W")
   - "CCT": Color temperature options (e.g., "3000K / 4000K / 5000K" or "3000K-5000K Selectable")
   - "CRI": Color Rendering Index (e.g., "≥80" or "80+")
   - "Beam Angle": Light distribution angle (e.g., "120°" or "Type III")
   - "Light Distribution": Distribution type (e.g., "Type III", "Type V", "Asymmetric")
   - "LED Source": LED chip type if mentioned (e.g., "High-Power LED" or "SMD LED")

9. physical_specs: Dict with keys:
   - "Housing Material": Material type (e.g., "Die-Cast Aluminum" or "Aluminum Alloy")
   - "Lens Material": Lens type (e.g., "Polycarbonate" or "Tempered Glass")
   - "Finish": Finish type and color (e.g., "Bronze" or "Black Powder Coating")
   - "Dimensions": Full dimensions L x W x H (e.g., "12.5\" x 8.5\" x 6.2\"")
   - "Weight": Net weight with units (e.g., "8.5 lbs" or "3.9 kg")
   - "Mounting Type": Mounting options (e.g., "Pole Mount" or "Wall Mount / Ceiling Mount")
   - "EPA": Effective Projected Area if available

10. environmental_specs: Dict with keys:
    - "IP Rating": Ingress Protection (e.g., "IP65" or "IP66")
    - "IK Rating": Impact Protection if available (e.g., "IK08")
    - "Operating Temperature": Full range (e.g., "-40°F to 140°F" or "-40°C to 60°C")
    - "Suitable Location": Location type (e.g., "Wet Location" or "Damp Location")

11. lifespan_specs: Dict with keys:
    - "Lifespan": Average life hours (e.g., "50,000 hours" or "L70 @ 50,000 hours")
    - "Warranty": Warranty period (e.g., "5 years" or "10 years")

12. certifications: List of certification strings. Be comprehensive. E.g. ["cETLus Listed", "DLC Premium", "IP65", "RoHS Compliant", "Energy Star"]
    - Include all safety certifications (UL, ETL, CE)
    - Include energy certifications (DLC, Energy Star)
    - Include environmental certifications (RoHS)
    - Include IP ratings if significant

13. warranty_text: One comprehensive professional sentence about the warranty.
    - Example: "5-year limited warranty covering defects in materials and workmanship under normal use and proper installation."
    - Include key limitations if mentioned

14. ordering_notes: Any important ordering information, part number structure, or notes (string, can be empty "")
    - Include part number format if available
    - Include ordering codes or options
    - Include any special instructions

INTELLIGENT INFERENCE RULES:
- INFER missing specifications: If product type is "Area Luminaire" and no IP rating → infer IP65 (standard for outdoor)
- INFER missing features: If CCT has multiple values → add "CCT Selectable", if dimming mentioned → add "Dimmable Control"
- INFER missing certifications: If IP65 outdoor product → likely add "UL Listed" or "ETL Listed", if high efficacy → likely "DLC Premium"
- INFER missing applications: Based on product type (e.g., "Area Luminaire" → "Parking Lots", "Loading Docks", "Perimeter Security")
- INFER missing materials: If outdoor IP65 → likely "Die-Cast Aluminum" housing, "Polycarbonate" lens
- INFER missing lifespan: If no lifespan mentioned but modern LED → infer "50,000 hours" or "L70 @ 50,000 hours"
- INFER missing warranty: If no warranty mentioned → infer "5 years" (industry standard)
- INFER missing power factor: If not mentioned → infer "≥0.9" (standard for quality LED products)
- INFER missing THD: If not mentioned → infer "<20%" (standard for quality LED drivers)

IMPORTANT:
- All spec values must include units (e.g. "100W" not "100", "5000K" not "5000")
- Use "/" to separate multiple options (e.g. "70W / 100W / 150W")
- Use ranges when appropriate (e.g., "3000K-5000K Selectable")
- Remove any non-English text completely
- BE INTELLIGENT - infer missing data based on product type and industry standards
- DO NOT just copy vendor data - enhance and make it unique and professional
- Infer related specifications when logical (e.g., if CCT is selectable, add "CCT Selectable" to features)
- Make content distinctive - rewrite descriptions to be more compelling and unique
- Return ONLY valid JSON, no markdown, no explanation

RAW VENDOR DATA:
"""


# ─────────────────────────────────────────────────────────────────────────────
# Enhancer class
# ─────────────────────────────────────────────────────────────────────────────
class AIContentEnhancer:
    """
    Uses the configured AI provider to intelligently enhance and rewrite
    extracted vendor spec data into professional IKIO TDS content.
    """

    def __init__(self, provider: Optional[str] = None, api_key: Optional[str] = None):
        try:
            self.client = get_ai_client(provider, api_key)
            self.available = True
            console.print(f"[green]✓ AI Enhancer ready: {type(self.client).__name__}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ AI Enhancer unavailable: {e}[/yellow]")
            self.client = None
            self.available = False

    def enhance(self, vendor_data: VendorSpecData) -> VendorSpecData:
        """
        Main entry point. Sends vendor data to AI, gets enhanced content back,
        and merges it into the VendorSpecData object.
        Returns the (possibly enhanced) VendorSpecData.
        """
        if not self.available or self.client is None:
            console.print("[yellow]⚠ Skipping AI enhancement (no client)[/yellow]")
            return vendor_data

        console.print("[cyan]🤖 Running AI content enhancement...[/cyan]")

        # Build a compact text summary of all extracted data
        raw_summary = self._build_raw_summary(vendor_data)

        try:
            # Call AI with the enhancement prompt
            full_prompt = ENHANCEMENT_PROMPT + raw_summary
            result = self.client.analyze_text(raw_summary, prompt=ENHANCEMENT_PROMPT)

            if "error" in result and "parse_error" not in result:
                console.print(f"[yellow]⚠ AI enhancement failed: {result.get('error')}[/yellow]")
                return vendor_data

            # Merge enhanced content back into vendor_data
            enhanced = self._merge_enhanced(vendor_data, result)
            console.print("[green]✓ AI enhancement complete![/green]")
            return enhanced

        except Exception as e:
            console.print(f"[yellow]⚠ AI enhancement error (using raw data): {e}[/yellow]")
            return vendor_data

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _build_raw_summary(self, vendor_data: VendorSpecData) -> str:
        """Convert VendorSpecData into a compact text block for the AI prompt."""
        lines = []

        lines.append(f"Product Name: {vendor_data.product_name or 'Unknown'}")
        lines.append(f"Product Series: {vendor_data.product_series or ''}")
        lines.append(f"Product Category: {vendor_data.product_category or ''}")
        lines.append(f"Model Numbers: {', '.join(vendor_data.model_numbers) if vendor_data.model_numbers else ''}")
        lines.append(f"Description: {vendor_data.product_description or ''}")
        lines.append(f"Tagline: {vendor_data.tagline or ''}")

        if vendor_data.features:
            lines.append("\nFeatures:")
            for f in vendor_data.features[:12]:
                lines.append(f"  - {f}")

        if vendor_data.applications:
            lines.append("\nApplications:")
            for a in vendor_data.applications[:8]:
                lines.append(f"  - {a}")

        def _fmt_specs(title: str, specs: dict):
            if specs:
                lines.append(f"\n{title}:")
                for k, v in specs.items():
                    lines.append(f"  {k}: {v}")

        _fmt_specs("Electrical Specs", vendor_data.electrical_specs)
        _fmt_specs("Optical Specs", vendor_data.optical_specs)
        _fmt_specs("Physical Specs", vendor_data.physical_specs)
        _fmt_specs("Environmental Specs", vendor_data.environmental_specs)
        _fmt_specs("Lifespan Specs", vendor_data.lifespan_specs)
        _fmt_specs("Component Specs", vendor_data.component_specs)

        if vendor_data.certifications:
            lines.append(f"\nCertifications: {', '.join(vendor_data.certifications)}")

        if vendor_data.ordering_info:
            lines.append(f"\nOrdering Info: {json.dumps(vendor_data.ordering_info)[:500]}")

        if vendor_data.packaging_info:
            lines.append(f"\nPackaging: {json.dumps(vendor_data.packaging_info)[:300]}")

        # Include raw tables as extra context
        if vendor_data.raw_tables:
            lines.append("\nRaw Tables (for context):")
            for table in vendor_data.raw_tables[:3]:
                if table.title:
                    lines.append(f"  Table: {table.title}")
                if table.headers:
                    lines.append(f"  Headers: {' | '.join(str(h) for h in table.headers)}")
                for row in table.rows[:5]:
                    lines.append(f"  Row: {' | '.join(str(c) for c in row)}")

        return "\n".join(lines)

    def _merge_enhanced(self, vendor_data: VendorSpecData, enhanced: dict) -> VendorSpecData:
        """
        Merge AI-enhanced fields back into the VendorSpecData object.
        Only overwrites fields if the enhanced value is non-empty.
        """
        def _nonempty(val) -> bool:
            if val is None:
                return False
            if isinstance(val, str):
                return bool(val.strip())
            if isinstance(val, (list, dict)):
                return bool(val)
            return True

        # ── String fields ──────────────────────────────────────────────────
        if _nonempty(enhanced.get("product_name")):
            vendor_data.product_name = str(enhanced["product_name"]).strip()

        if _nonempty(enhanced.get("product_category")):
            vendor_data.product_category = str(enhanced["product_category"]).strip()

        if _nonempty(enhanced.get("product_description")):
            vendor_data.product_description = str(enhanced["product_description"]).strip()

        if _nonempty(enhanced.get("tagline")):
            vendor_data.tagline = str(enhanced["tagline"]).strip()

        # ── List fields ────────────────────────────────────────────────────
        if _nonempty(enhanced.get("features")):
            raw_features = enhanced["features"]
            if isinstance(raw_features, list):
                vendor_data.features = [str(f).strip() for f in raw_features if str(f).strip()]

        if _nonempty(enhanced.get("applications")):
            raw_apps = enhanced["applications"]
            if isinstance(raw_apps, list):
                vendor_data.applications = [str(a).strip() for a in raw_apps if str(a).strip()]

        if _nonempty(enhanced.get("certifications")):
            raw_certs = enhanced["certifications"]
            if isinstance(raw_certs, list):
                vendor_data.certifications = [str(c).strip() for c in raw_certs if str(c).strip()]

        # ── Spec dicts ─────────────────────────────────────────────────────
        def _merge_spec_dict(enhanced_key: str, target: dict):
            src = enhanced.get(enhanced_key, {})
            if isinstance(src, dict):
                for k, v in src.items():
                    if _nonempty(v):
                        target[k] = str(v).strip()

        _merge_spec_dict("electrical_specs", vendor_data.electrical_specs)
        _merge_spec_dict("optical_specs", vendor_data.optical_specs)
        _merge_spec_dict("physical_specs", vendor_data.physical_specs)
        _merge_spec_dict("environmental_specs", vendor_data.environmental_specs)
        _merge_spec_dict("lifespan_specs", vendor_data.lifespan_specs)

        # ── Extra fields stored in lifespan_specs for downstream use ───────
        if _nonempty(enhanced.get("warranty_text")):
            vendor_data.lifespan_specs["Warranty Text"] = str(enhanced["warranty_text"]).strip()

        if _nonempty(enhanced.get("ordering_notes")):
            vendor_data.ordering_info["notes"] = str(enhanced["ordering_notes"]).strip()

        return vendor_data


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function
# ─────────────────────────────────────────────────────────────────────────────
def enhance_vendor_data(
    vendor_data: VendorSpecData,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
) -> VendorSpecData:
    """
    Convenience wrapper. Call this after process_vendor_spec() and before map_vendor_to_tds().
    """
    enhancer = AIContentEnhancer(provider=provider, api_key=api_key)
    return enhancer.enhance(vendor_data)
