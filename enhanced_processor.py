"""
Enhanced Document Processor - Combines Deep Learning OCR with AI Understanding
Uses docTR/PaddleOCR for accurate text extraction and AI for semantic analysis
"""
import json
import io
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from PIL import Image
import fitz
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from doctr_processor import DocTRProcessor, DocumentLayout, TextBlock, DetectedTable, DetectedImage
from ai_vision_processor import VendorSpecData, ExtractedImage, ExtractedTable
from ai_client import get_ai_client

console = Console()


class EnhancedDocumentProcessor:
    """
    Enhanced processor that combines:
    1. docTR/PaddleOCR for accurate OCR and layout detection
    2. AI (Gemini/GPT/Groq) for semantic understanding
    3. Rule-based extraction for structured data
    """
    
    def __init__(self, provider: Optional[str] = None, api_key: Optional[str] = None, use_gpu: bool = False):
        # Initialize docTR processor
        console.print("[cyan]Initializing Enhanced Document Processor...[/cyan]")
        self.doctr = DocTRProcessor(use_gpu=use_gpu)
        
        # Initialize AI client for semantic analysis
        self.ai_client = get_ai_client(provider, api_key)
        console.print(f"[green]✓ AI Client: {type(self.ai_client).__name__}[/green]")
        
        # Extraction patterns
        self._init_patterns()
    
    def _init_patterns(self):
        """Initialize extraction patterns for specifications"""
        self.spec_keywords = {
            'product_name': [
                r'(?i)^([A-Z][A-Za-z0-9\s\-]+(?:LED|Light|Lamp|Fixture|Panel|Downlight|Strip|Flood|Bay|Street))',
                r'(?i)model\s*[:\-]?\s*([A-Z0-9\-]+)',
            ],
            'wattage': [
                r'(\d+(?:\.\d+)?)\s*W(?:att)?(?:s)?\b',
                r'(?i)power\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*W',
                r'(?i)wattage\s*[:\-]?\s*(\d+(?:\.\d+)?)',
            ],
            'voltage': [
                r'(\d+(?:\-\d+)?)\s*V(?:\s*(?:AC|DC))?',
                r'(?i)(?:input\s*)?voltage\s*[:\-]?\s*(\d+(?:\-\d+)?\s*V)',
            ],
            'lumens': [
                r'(\d+(?:,\d+)?)\s*(?:lm|lumens?)\b',
                r'(?i)(?:luminous\s*flux|lumens?)\s*[:\-]?\s*(\d+(?:,\d+)?)',
            ],
            'efficacy': [
                r'(\d+(?:\.\d+)?)\s*(?:lm\/W|lm/W)\b',
                r'(?i)efficacy\s*[:\-]?\s*(\d+(?:\.\d+)?)',
            ],
            'cct': [
                r'(\d{4})\s*K\b',
                r'(?i)(?:cct|color\s*temp(?:erature)?)\s*[:\-]?\s*(\d{4})\s*K',
            ],
            'cri': [
                r'(?i)cri\s*[:\->]?\s*(\d+)',
                r'(?i)(?:ra|color\s*rendering)\s*[:\->]?\s*(\d+)',
            ],
            'beam_angle': [
                r'(\d+)\s*°',
                r'(?i)beam\s*(?:angle)?\s*[:\-]?\s*(\d+)',
            ],
            'ip_rating': [
                r'IP\s*(\d{2})',
                r'(?i)(?:ingress\s*protection|ip)\s*[:\-]?\s*IP?\s*(\d{2})',
            ],
            'ik_rating': [
                r'IK\s*(\d{1,2})',
            ],
            'lifespan': [
                r'(\d+(?:,\d+)?)\s*(?:hours?|hrs?|H)\b',
                r'(?i)(?:life(?:span)?|l70|l80)\s*[:\-]?\s*(\d+(?:,\d+)?)',
            ],
            'warranty': [
                r'(\d+)\s*(?:years?|yrs?)\s*(?:warranty)?',
                r'(?i)warranty\s*[:\-]?\s*(\d+)',
            ],
            'dimensions': [
                r'(\d+(?:\.\d+)?\s*[×xX]\s*\d+(?:\.\d+)?(?:\s*[×xX]\s*\d+(?:\.\d+)?)?)\s*(?:mm|cm|in)?',
            ],
            'weight': [
                r'(\d+(?:\.\d+)?)\s*(?:kg|g|lbs?)',
            ],
            'power_factor': [
                r'(?i)(?:power\s*factor|pf)\s*[:\->]?\s*([>]?\s*[\d\.]+)',
            ],
        }
    
    def process_vendor_spec(self, pdf_path: str) -> VendorSpecData:
        """
        Process vendor specification sheet with enhanced extraction
        
        Steps:
        1. Use docTR for accurate OCR and layout detection
        2. Extract structured data using patterns
        3. Use AI for semantic understanding and filling gaps
        4. Classify and extract images
        """
        pdf_path = Path(pdf_path)
        console.print(f"\n[bold cyan]═══ Processing: {pdf_path.name} ═══[/bold cyan]")
        
        # Step 1: Document layout analysis with docTR
        console.print("\n[cyan]Step 1: Deep Learning OCR & Layout Analysis[/cyan]")
        layout = self.doctr.process_document(str(pdf_path))
        
        # Step 2: Extract structured data with patterns
        console.print("\n[cyan]Step 2: Pattern-based Specification Extraction[/cyan]")
        extracted_data = self._extract_structured_data(layout)
        
        # Step 3: AI semantic analysis
        console.print("\n[cyan]Step 3: AI Semantic Analysis[/cyan]")
        extracted_data = self._enhance_with_ai(layout, extracted_data)
        
        # Step 4: Extract and classify images
        console.print("\n[cyan]Step 4: Image Extraction & Classification[/cyan]")
        extracted_data = self._process_images(pdf_path, layout, extracted_data)
        
        # Step 5: Post-processing and validation
        console.print("\n[cyan]Step 5: Post-processing & Validation[/cyan]")
        extracted_data = self._post_process(extracted_data)
        
        # Calculate confidence
        extracted_data.extraction_confidence = self._calculate_confidence(extracted_data)
        
        console.print(f"\n[bold green]✓ Extraction Complete![/bold green]")
        console.print(f"  Product: {extracted_data.product_name}")
        console.print(f"  Confidence: {extracted_data.extraction_confidence:.1%}")
        console.print(f"  Features: {len(extracted_data.features)}")
        console.print(f"  Images: {len(extracted_data.images)}")
        
        return extracted_data
    
    def _extract_structured_data(self, layout: DocumentLayout) -> VendorSpecData:
        """Extract structured data from document layout using patterns"""
        data = VendorSpecData()
        data.page_count = layout.page_count
        
        full_text = layout.full_text
        
        # Extract product name
        for pattern in self.spec_keywords['product_name']:
            match = re.search(pattern, full_text)
            if match:
                data.product_name = match.group(1).strip()
                break
        
        # Extract specifications
        self._extract_specs_from_text(full_text, data)
        
        # Extract from detected tables
        for table in layout.tables:
            self._extract_from_table(table, data)
        
        # Extract features and applications from sections
        features, applications = self.doctr.extract_features_applications(layout)
        data.features = features
        data.applications = applications
        
        # Extract from sections
        if 'certifications' in layout.sections:
            for block in layout.sections['certifications']:
                certs = re.findall(r'\b(CE|UL|ETL|DLC|RoHS|FCC|IC|cETLus|Energy\s*Star)\b', 
                                  block.text, re.IGNORECASE)
                data.certifications.extend([c.upper() for c in certs if c.upper() not in data.certifications])
        
        console.print(f"  [green]✓ Extracted {len(data.electrical_specs)} electrical specs[/green]")
        console.print(f"  [green]✓ Extracted {len(data.optical_specs)} optical specs[/green]")
        console.print(f"  [green]✓ Extracted {len(data.features)} features[/green]")
        
        return data
    
    def _extract_specs_from_text(self, text: str, data: VendorSpecData):
        """Extract specifications from text using patterns"""
        
        # Electrical specs
        for pattern in self.spec_keywords['wattage']:
            match = re.search(pattern, text)
            if match:
                data.electrical_specs['Power'] = f"{match.group(1)}W"
                break
        
        for pattern in self.spec_keywords['voltage']:
            match = re.search(pattern, text)
            if match:
                data.electrical_specs['Voltage'] = match.group(1)
                break
        
        for pattern in self.spec_keywords['power_factor']:
            match = re.search(pattern, text)
            if match:
                data.electrical_specs['Power Factor'] = match.group(1)
                break
        
        # Optical specs
        for pattern in self.spec_keywords['lumens']:
            match = re.search(pattern, text)
            if match:
                data.optical_specs['Lumens'] = f"{match.group(1).replace(',', '')}lm"
                break
        
        for pattern in self.spec_keywords['efficacy']:
            match = re.search(pattern, text)
            if match:
                data.optical_specs['Efficacy'] = f"{match.group(1)}lm/W"
                break
        
        for pattern in self.spec_keywords['cct']:
            matches = re.findall(pattern, text)
            if matches:
                ccts = sorted(set(matches))
                data.optical_specs['CCT'] = " / ".join([f"{c}K" for c in ccts])
                break
        
        for pattern in self.spec_keywords['cri']:
            match = re.search(pattern, text)
            if match:
                data.optical_specs['CRI'] = f">{match.group(1)}"
                break
        
        for pattern in self.spec_keywords['beam_angle']:
            match = re.search(pattern, text)
            if match:
                data.optical_specs['Beam Angle'] = f"{match.group(1)}°"
                break
        
        # Environmental specs
        for pattern in self.spec_keywords['ip_rating']:
            match = re.search(pattern, text)
            if match:
                data.environmental_specs['IP Rating'] = f"IP{match.group(1)}"
                break
        
        for pattern in self.spec_keywords['ik_rating']:
            match = re.search(pattern, text)
            if match:
                data.environmental_specs['IK Rating'] = f"IK{match.group(1)}"
                break
        
        # Physical specs
        for pattern in self.spec_keywords['dimensions']:
            match = re.search(pattern, text)
            if match:
                data.physical_specs['Dimensions'] = match.group(1)
                break
        
        for pattern in self.spec_keywords['weight']:
            match = re.search(pattern, text)
            if match:
                data.physical_specs['Weight'] = match.group(1)
                break
        
        # Lifespan specs
        for pattern in self.spec_keywords['lifespan']:
            match = re.search(pattern, text)
            if match:
                hours = match.group(1).replace(',', '')
                data.lifespan_specs['Lifespan'] = f"{hours} hours"
                break
        
        for pattern in self.spec_keywords['warranty']:
            match = re.search(pattern, text)
            if match:
                data.lifespan_specs['Warranty'] = f"{match.group(1)} Years"
                break
    
    def _extract_from_table(self, table: DetectedTable, data: VendorSpecData):
        """Extract specifications from detected table"""
        for row in table.rows:
            if len(row) >= 2:
                key = row[0].lower().strip()
                value = row[1].strip()
                
                if not value:
                    continue
                
                # Categorize based on key
                if any(x in key for x in ['power', 'watt', 'voltage', 'current', 'factor']):
                    data.electrical_specs[row[0]] = value
                elif any(x in key for x in ['lumen', 'efficacy', 'cct', 'cri', 'beam', 'color']):
                    data.optical_specs[row[0]] = value
                elif any(x in key for x in ['dimension', 'weight', 'size', 'material', 'housing']):
                    data.physical_specs[row[0]] = value
                elif any(x in key for x in ['ip', 'ik', 'temp', 'humidity', 'rating']):
                    data.environmental_specs[row[0]] = value
                elif any(x in key for x in ['life', 'warranty', 'hours']):
                    data.lifespan_specs[row[0]] = value
    
    def _enhance_with_ai(self, layout: DocumentLayout, data: VendorSpecData) -> VendorSpecData:
        """Use AI to enhance extraction with semantic understanding"""
        
        # Prepare structured text for AI
        structured_text = self._prepare_text_for_ai(layout, data)
        
        # Create targeted prompts for missing data
        prompts_needed = []
        
        if not data.product_name:
            prompts_needed.append("product_name")
        if not data.product_description:
            prompts_needed.append("description")
        if len(data.features) < 3:
            prompts_needed.append("features")
        if len(data.applications) < 2:
            prompts_needed.append("applications")
        
        if not prompts_needed:
            console.print("  [green]✓ All key fields extracted, minimal AI needed[/green]")
            return data
        
        # Use AI to fill gaps
        prompt = self._create_extraction_prompt(structured_text, prompts_needed)
        
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Analyzing with AI...", total=None)
                
                if self.ai_client.supports_vision:
                    # Send first page image for visual context
                    ai_result = self.ai_client.analyze_text(prompt)
                else:
                    ai_result = self.ai_client.analyze_text(prompt)
                
                progress.update(task, description="AI analysis complete")
            
            # Merge AI results with extracted data
            data = self._merge_ai_results(ai_result, data)
            console.print(f"  [green]✓ AI enhanced {len(prompts_needed)} fields[/green]")
            
        except Exception as e:
            console.print(f"  [yellow]Warning: AI enhancement failed: {e}[/yellow]")
        
        return data
    
    def _prepare_text_for_ai(self, layout: DocumentLayout, data: VendorSpecData) -> str:
        """Prepare structured text summary for AI"""
        sections = []
        
        sections.append("=== DOCUMENT TEXT ===")
        sections.append(layout.full_text[:5000])  # First 5000 chars
        
        sections.append("\n=== ALREADY EXTRACTED ===")
        if data.product_name:
            sections.append(f"Product Name: {data.product_name}")
        if data.electrical_specs:
            sections.append(f"Electrical: {json.dumps(data.electrical_specs)}")
        if data.optical_specs:
            sections.append(f"Optical: {json.dumps(data.optical_specs)}")
        
        return "\n".join(sections)
    
    def _create_extraction_prompt(self, text: str, needed_fields: List[str]) -> str:
        """Create targeted extraction prompt for AI"""
        prompt = f"""Analyze this LED lighting product specification document and extract the following information.
Return ONLY a valid JSON object with the requested fields.

DOCUMENT:
{text}

EXTRACT THESE FIELDS:
"""
        
        if "product_name" in needed_fields:
            prompt += "- product_name: The full product name/model\n"
        if "description" in needed_fields:
            prompt += "- product_description: A 2-3 sentence description of the product\n"
        if "features" in needed_fields:
            prompt += "- features: Array of key product features (at least 5)\n"
        if "applications" in needed_fields:
            prompt += "- applications: Array of application areas/uses\n"
        
        prompt += """
Return ONLY valid JSON like:
{
  "product_name": "...",
  "product_description": "...",
  "features": ["...", "..."],
  "applications": ["...", "..."]
}"""
        
        return prompt
    
    def _merge_ai_results(self, ai_result: Dict, data: VendorSpecData) -> VendorSpecData:
        """Merge AI extraction results with existing data"""
        if not ai_result or "error" in ai_result:
            return data
        
        if ai_result.get("product_name") and not data.product_name:
            data.product_name = str(ai_result["product_name"])
        
        if ai_result.get("product_description") and not data.product_description:
            data.product_description = str(ai_result["product_description"])
        
        if ai_result.get("features"):
            features = ai_result["features"]
            if isinstance(features, list):
                for f in features:
                    if f and str(f) not in data.features:
                        data.features.append(str(f))
        
        if ai_result.get("applications"):
            apps = ai_result["applications"]
            if isinstance(apps, list):
                for a in apps:
                    if a and str(a) not in data.applications:
                        data.applications.append(str(a))
        
        return data
    
    def _process_images(self, pdf_path: Path, layout: DocumentLayout, data: VendorSpecData) -> VendorSpecData:
        """Process and classify images from the document"""
        
        # Open PDF for image extraction
        doc = fitz.open(pdf_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            for img in image_list:
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    width, height = pil_image.size
                    
                    # Skip small images
                    if width < 80 or height < 80:
                        continue
                    
                    # Classify image
                    image_type = self._classify_image_enhanced(pil_image, width, height)
                    
                    extracted_img = ExtractedImage(
                        page_number=page_num + 1,
                        image_data=image_bytes,
                        image_type=image_type,
                        width=width,
                        height=height
                    )
                    
                    data.images.append(extracted_img)
                    
                    # Assign to specific fields
                    if image_type == "dimension":
                        if not data.dimension_diagram:
                            data.dimension_diagram = extracted_img
                    elif image_type == "beam_pattern":
                        data.beam_angle_diagrams.append(extracted_img)
                    elif image_type == "wiring":
                        data.wiring_diagrams.append(extracted_img)
                    
                except Exception as e:
                    continue
        
        doc.close()
        
        console.print(f"  [green]✓ Processed {len(data.images)} images[/green]")
        console.print(f"    - Product images: {len([i for i in data.images if i.image_type == 'product'])}")
        console.print(f"    - Dimension diagrams: {1 if data.dimension_diagram else 0}")
        console.print(f"    - Beam patterns: {len(data.beam_angle_diagrams)}")
        
        return data
    
    def _classify_image_enhanced(self, img: Image.Image, width: int, height: int) -> str:
        """Enhanced image classification"""
        import numpy as np
        
        aspect_ratio = width / max(height, 1)
        
        # Convert to grayscale for analysis
        gray = img.convert('L')
        img_array = np.array(gray)
        
        # Calculate image statistics
        mean_val = np.mean(img_array)
        std_val = np.std(img_array)
        
        # Edge detection (simple gradient)
        grad_x = np.abs(np.diff(img_array.astype(float), axis=1)).mean()
        grad_y = np.abs(np.diff(img_array.astype(float), axis=0)).mean()
        edge_strength = (grad_x + grad_y) / 2
        
        # Wide images with patterns = beam diagrams
        if aspect_ratio > 1.8 and std_val > 40:
            return "beam_pattern"
        
        # High edge content with lines = dimension diagram
        if edge_strength > 15 and 0.5 < aspect_ratio < 2.0 and width > 200:
            # Check for line-like structures
            if std_val > 50:
                return "dimension"
        
        # Dark images with symbols = wiring diagrams
        if mean_val < 150 and std_val > 60 and width > 150:
            return "wiring"
        
        # Square-ish, moderate size = product image
        if 0.6 < aspect_ratio < 1.6 and width > 150 and height > 150:
            return "product"
        
        # Small images = accessories
        if width < 200 or height < 200:
            return "accessory"
        
        return "product"
    
    def _post_process(self, data: VendorSpecData) -> VendorSpecData:
        """Post-process and validate extracted data"""
        
        # Clean and deduplicate features
        data.features = list(dict.fromkeys([f.strip() for f in data.features if f.strip()]))[:12]
        
        # Clean applications
        data.applications = list(dict.fromkeys([a.strip() for a in data.applications if a.strip()]))[:10]
        
        # Clean certifications
        data.certifications = list(dict.fromkeys([c.upper() for c in data.certifications]))
        
        # Ensure product name is clean
        if data.product_name:
            data.product_name = re.sub(r'\s+', ' ', data.product_name).strip()
        
        # Generate category if missing
        if not data.product_category and data.product_name:
            data.product_category = self._infer_category(data.product_name)
        
        console.print(f"  [green]✓ Post-processing complete[/green]")
        
        return data
    
    def _infer_category(self, product_name: str) -> str:
        """Infer product category from name"""
        name_lower = product_name.lower()
        
        categories = {
            'downlight': 'LED DOWNLIGHT',
            'panel': 'LED PANEL',
            'flood': 'LED FLOOD LIGHT',
            'street': 'LED STREET LIGHT',
            'high bay': 'LED HIGH BAY',
            'highbay': 'LED HIGH BAY',
            'strip': 'LED STRIP LIGHT',
            'tube': 'LED TUBE',
            'bulb': 'LED BULB',
            'spot': 'LED SPOT LIGHT',
            'track': 'LED TRACK LIGHT',
            'canopy': 'LED CANOPY LIGHT',
            'wall': 'LED WALL PACK',
            'area': 'LED AREA LIGHT',
            'stadium': 'LED STADIUM LIGHT',
        }
        
        for keyword, category in categories.items():
            if keyword in name_lower:
                return category
        
        return "LED LIGHTING"
    
    def _calculate_confidence(self, data: VendorSpecData) -> float:
        """Calculate extraction confidence score"""
        score = 0.0
        max_score = 12.0
        
        if data.product_name:
            score += 2.0
        if data.product_description:
            score += 1.5
        if len(data.features) >= 5:
            score += 1.5
        elif len(data.features) >= 3:
            score += 1.0
        if len(data.applications) >= 3:
            score += 1.0
        if len(data.electrical_specs) >= 3:
            score += 1.5
        if len(data.optical_specs) >= 3:
            score += 1.5
        if len(data.physical_specs) >= 2:
            score += 1.0
        if len(data.environmental_specs) >= 1:
            score += 0.5
        if len(data.certifications) >= 2:
            score += 0.5
        if data.dimension_diagram:
            score += 0.5
        if data.images:
            score += 0.5
        
        return min(score / max_score, 1.0)


def process_enhanced(pdf_path: str, provider: Optional[str] = None, api_key: Optional[str] = None) -> VendorSpecData:
    """
    Convenience function to process a vendor spec sheet with enhanced extraction.
    
    Args:
        pdf_path: Path to the vendor PDF
        provider: Optional AI provider ("groq", "gemini", "ollama", "openai")
        api_key: Optional API key
    """
    processor = EnhancedDocumentProcessor(provider=provider, api_key=api_key)
    return processor.process_vendor_spec(pdf_path)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        result = process_enhanced(sys.argv[1])
        
        print("\n" + "="*50)
        print("EXTRACTION RESULTS")
        print("="*50)
        print(f"Product: {result.product_name}")
        print(f"Category: {result.product_category}")
        print(f"Description: {result.product_description[:200]}...")
        print(f"\nFeatures ({len(result.features)}):")
        for f in result.features[:5]:
            print(f"  • {f}")
        print(f"\nElectrical Specs: {json.dumps(result.electrical_specs, indent=2)}")
        print(f"\nOptical Specs: {json.dumps(result.optical_specs, indent=2)}")
        print(f"\nImages: {len(result.images)}")
        print(f"Confidence: {result.extraction_confidence:.1%}")
    else:
        print("Usage: python enhanced_processor.py <vendor_spec.pdf>")

