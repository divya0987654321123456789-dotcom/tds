"""
PDF Text and Data Extractor Module
Extracts specifications, tables, and structured data from client PDFs
"""
import fitz  # PyMuPDF
import pdfplumber
from pathlib import Path
from typing import Dict, List, Any, Optional
import re
import json
from dataclasses import dataclass, asdict
from rich.console import Console

console = Console()


@dataclass
class ExtractedTable:
    """Represents an extracted table from PDF"""
    page_number: int
    headers: List[str]
    rows: List[List[str]]
    context: str = ""


@dataclass
class ExtractedSpec:
    """Represents extracted specification data"""
    raw_text: str
    tables: List[ExtractedTable]
    images_info: List[Dict]
    metadata: Dict[str, Any]
    structured_data: Dict[str, Any]


class PDFExtractor:
    """
    Comprehensive PDF extractor that handles various PDF formats
    and extracts specifications intelligently
    """
    
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        self.doc = None
        self.plumber_pdf = None
        
    def __enter__(self):
        self.doc = fitz.open(self.pdf_path)
        self.plumber_pdf = pdfplumber.open(self.pdf_path)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.doc:
            self.doc.close()
        if self.plumber_pdf:
            self.plumber_pdf.close()
    
    def extract_all(self) -> ExtractedSpec:
        """Extract all data from the PDF"""
        console.print(f"[cyan]Extracting data from: {self.pdf_path.name}[/cyan]")
        
        raw_text = self._extract_text()
        tables = self._extract_tables()
        images_info = self._extract_images_info()
        metadata = self._extract_metadata()
        structured_data = self._parse_specifications(raw_text)
        
        return ExtractedSpec(
            raw_text=raw_text,
            tables=tables,
            images_info=images_info,
            metadata=metadata,
            structured_data=structured_data
        )
    
    def _extract_text(self) -> str:
        """Extract all text from PDF with formatting preservation"""
        full_text = []
        
        for page_num, page in enumerate(self.doc):
            # Get text with layout preservation
            text = page.get_text("text")
            full_text.append(f"\n--- Page {page_num + 1} ---\n{text}")
            
            # Also try blocks for better structure
            blocks = page.get_text("blocks")
            for block in blocks:
                if block[6] == 0:  # Text block
                    pass  # Already captured in main text
        
        return "\n".join(full_text)
    
    def _extract_tables(self) -> List[ExtractedTable]:
        """Extract tables from PDF using pdfplumber"""
        extracted_tables = []
        
        for page_num, page in enumerate(self.plumber_pdf.pages):
            tables = page.extract_tables()
            
            for table in tables:
                if table and len(table) > 0:
                    # First row is usually headers
                    headers = [str(cell).strip() if cell else "" for cell in table[0]]
                    rows = []
                    
                    for row in table[1:]:
                        cleaned_row = [str(cell).strip() if cell else "" for cell in row]
                        if any(cleaned_row):  # Skip empty rows
                            rows.append(cleaned_row)
                    
                    if headers or rows:
                        extracted_tables.append(ExtractedTable(
                            page_number=page_num + 1,
                            headers=headers,
                            rows=rows,
                            context=self._get_table_context(page, table)
                        ))
        
        return extracted_tables
    
    def _get_table_context(self, page, table) -> str:
        """Get text around the table for context"""
        # Simple approach: get some text from the page
        text = page.extract_text() or ""
        # Return first 200 chars as context
        return text[:200] if text else ""
    
    def _extract_images_info(self) -> List[Dict]:
        """Extract information about images in the PDF"""
        images_info = []
        
        for page_num, page in enumerate(self.doc):
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                images_info.append({
                    "page": page_num + 1,
                    "xref": xref,
                    "width": img[2],
                    "height": img[3],
                    "index": img_index
                })
        
        return images_info
    
    def _extract_metadata(self) -> Dict[str, Any]:
        """Extract PDF metadata"""
        metadata = self.doc.metadata
        return {
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "subject": metadata.get("subject", ""),
            "creator": metadata.get("creator", ""),
            "producer": metadata.get("producer", ""),
            "page_count": len(self.doc),
            "file_name": self.pdf_path.name
        }
    
    def _parse_specifications(self, text: str) -> Dict[str, Any]:
        """Parse raw text to extract structured specifications"""
        specs = {
            "electrical": {},
            "optical": {},
            "physical": {},
            "environmental": {},
            "certifications": [],
            "features": [],
            "model_info": {}
        }
        
        # Common patterns for specification extraction
        patterns = {
            # Electrical
            "wattage": r"(?:Power|Wattage|Watts?)[:\s]*(\d+(?:\.\d+)?)\s*[Ww]",
            "voltage": r"(?:Voltage|Input)[:\s]*(\d+(?:-\d+)?)\s*[Vv](?:AC|DC)?",
            "current": r"(?:Current)[:\s]*(\d+(?:\.\d+)?)\s*[mM]?[Aa]",
            "power_factor": r"(?:Power Factor|PF)[:\s]*[>≥]?\s*(\d+(?:\.\d+)?)",
            "frequency": r"(?:Frequency)[:\s]*(\d+(?:-\d+)?)\s*[Hh][Zz]",
            
            # Optical
            "lumens": r"(?:Lumens?|Luminous Flux|Output)[:\s]*(\d+(?:,\d+)?)\s*[Ll]m",
            "efficacy": r"(?:Efficacy|Efficiency)[:\s]*(\d+(?:\.\d+)?)\s*[Ll]m\/[Ww]",
            "cct": r"(?:CCT|Color Temp(?:erature)?)[:\s]*(\d+)\s*[Kk]",
            "cri": r"(?:CRI|Ra)[:\s]*[>≥]?\s*(\d+)",
            "beam_angle": r"(?:Beam Angle)[:\s]*(\d+)[°]?",
            
            # Physical
            "dimensions": r"(?:Dimensions?|Size)[:\s]*([\d.]+\s*[xX×]\s*[\d.]+(?:\s*[xX×]\s*[\d.]+)?)\s*(?:mm|cm|in)?",
            "weight": r"(?:Weight|Mass)[:\s]*(\d+(?:\.\d+)?)\s*(?:kg|g|lbs?)",
            "material": r"(?:Material|Body|Housing)[:\s]*([A-Za-z\s]+?)(?:\n|,|;)",
            
            # Environmental
            "ip_rating": r"(?:IP\s*Rating|Protection)[:\s]*(IP\d{2})",
            "ik_rating": r"(?:IK\s*Rating|Impact)[:\s]*(IK\d{2})",
            "operating_temp": r"(?:Operating Temp(?:erature)?)[:\s]*(-?\d+)[°]?[Cc]?\s*(?:to|~|-)\s*(-?\d+)[°]?[Cc]?",
            "lifespan": r"(?:Lifespan|Life|L70)[:\s]*(\d+(?:,\d+)?)\s*(?:hours?|hrs?|h)",
        }
        
        # Extract values using patterns
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if key in ["wattage", "voltage", "current", "power_factor", "frequency"]:
                    specs["electrical"][key] = match.group(1)
                elif key in ["lumens", "efficacy", "cct", "cri", "beam_angle"]:
                    specs["optical"][key] = match.group(1)
                elif key in ["dimensions", "weight", "material"]:
                    specs["physical"][key] = match.group(1)
                elif key in ["ip_rating", "ik_rating", "lifespan"]:
                    specs["environmental"][key] = match.group(1)
                elif key == "operating_temp":
                    specs["environmental"]["operating_temp"] = f"{match.group(1)}°C to {match.group(2)}°C"
        
        # Extract certifications
        cert_patterns = [
            r"\b(CE)\b", r"\b(UL)\b", r"\b(RoHS)\b", r"\b(ETL)\b", 
            r"\b(DLC)\b", r"\b(Energy Star)\b", r"\b(BIS)\b", r"\b(ISI)\b"
        ]
        for pattern in cert_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                cert = re.search(pattern, text, re.IGNORECASE).group(1)
                if cert not in specs["certifications"]:
                    specs["certifications"].append(cert)
        
        # Extract model number
        model_match = re.search(r"(?:Model|Part\s*(?:No|Number)?)[:\s]*([A-Z0-9\-_]+)", text, re.IGNORECASE)
        if model_match:
            specs["model_info"]["model_number"] = model_match.group(1)
        
        return specs
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert extracted data to dictionary for JSON serialization"""
        extracted = self.extract_all()
        return {
            "raw_text": extracted.raw_text,
            "tables": [asdict(t) for t in extracted.tables],
            "images_info": extracted.images_info,
            "metadata": extracted.metadata,
            "structured_data": extracted.structured_data
        }


def extract_from_pdf(pdf_path: str) -> Dict[str, Any]:
    """Convenience function to extract data from PDF"""
    with PDFExtractor(pdf_path) as extractor:
        return extractor.to_dict()


if __name__ == "__main__":
    # Test extraction
    import sys
    if len(sys.argv) > 1:
        result = extract_from_pdf(sys.argv[1])
        print(json.dumps(result, indent=2, default=str))

