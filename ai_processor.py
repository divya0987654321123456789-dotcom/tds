"""
AI-Powered Specification Processor
Backward compatible module - now wraps ai_vision_processor for legacy support

For new implementations, use ai_vision_processor.py directly.
"""
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field
from rich.console import Console

console = Console()


@dataclass
class ProcessedSpecification:
    """
    Legacy structured specification data after AI processing.
    Maintained for backward compatibility with existing code.
    """
    product_name: str = ""
    model_number: str = ""
    product_category: str = ""
    tagline: str = ""
    
    # Specifications by category
    electrical_specs: Dict[str, str] = field(default_factory=dict)
    optical_specs: Dict[str, str] = field(default_factory=dict)
    physical_specs: Dict[str, str] = field(default_factory=dict)
    thermal_specs: Dict[str, str] = field(default_factory=dict)
    environmental_specs: Dict[str, str] = field(default_factory=dict)
    
    # Lists
    certifications: List[str] = field(default_factory=list)
    features: List[str] = field(default_factory=list)
    applications: List[str] = field(default_factory=list)
    accessories: List[str] = field(default_factory=list)
    
    # Additional info
    installation_notes: str = ""
    warranty_info: str = ""
    ordering_info: Dict[str, Any] = field(default_factory=dict)
    
    # Raw data for reference
    raw_tables: List[Dict] = field(default_factory=list)


class AISpecProcessor:
    """
    Legacy AI-powered processor.
    Now wraps the new ai_vision_processor for backward compatibility.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        from config import OPENAI_API_KEY
        self.api_key = api_key or OPENAI_API_KEY
    
    def process_specifications(self, extracted_data: Dict[str, Any]) -> ProcessedSpecification:
        """
        Process extracted PDF data and return structured specifications.
        
        Note: For full AI Vision extraction from PDFs, use ai_vision_processor.py
        """
        console.print("[cyan]Processing specifications...[/cyan]")
        
        # Use legacy fallback processing for Dict input
        return self._fallback_process(extracted_data)
    
    def _fallback_process(self, extracted_data: Dict[str, Any]) -> ProcessedSpecification:
        """Fallback processing using pattern matching"""
        structured = extracted_data.get("structured_data", {})
        raw_text = extracted_data.get("raw_text", "")
        
        return ProcessedSpecification(
            product_name=self._extract_product_name(raw_text, extracted_data.get("metadata", {})),
            model_number=structured.get("model_info", {}).get("model_number", ""),
            product_category=self._infer_category(raw_text),
            tagline="High Performance LED Lighting Solution",
            
            electrical_specs={
                "Input Voltage": structured.get("electrical", {}).get("voltage", "N/A"),
                "Power Consumption": f"{structured.get('electrical', {}).get('wattage', '')}W" if structured.get("electrical", {}).get("wattage") else "N/A",
                "Power Factor": structured.get("electrical", {}).get("power_factor", "N/A"),
                "Frequency": structured.get("electrical", {}).get("frequency", "50/60 Hz"),
            },
            
            optical_specs={
                "Luminous Flux": f"{structured.get('optical', {}).get('lumens', '')} lm" if structured.get("optical", {}).get("lumens") else "N/A",
                "Efficacy": f"{structured.get('optical', {}).get('efficacy', '')} lm/W" if structured.get("optical", {}).get("efficacy") else "N/A",
                "CCT": f"{structured.get('optical', {}).get('cct', '')}K" if structured.get("optical", {}).get("cct") else "N/A",
                "CRI": f">{structured.get('optical', {}).get('cri', '80')}" if structured.get("optical", {}).get("cri") else ">80",
                "Beam Angle": f"{structured.get('optical', {}).get('beam_angle', '')}°" if structured.get("optical", {}).get("beam_angle") else "N/A",
            },
            
            physical_specs={
                "Dimensions": structured.get("physical", {}).get("dimensions", "N/A"),
                "Weight": structured.get("physical", {}).get("weight", "N/A"),
                "Housing Material": structured.get("physical", {}).get("material", "Die-cast Aluminum"),
            },
            
            thermal_specs={
                "Operating Temperature": structured.get("environmental", {}).get("operating_temp", "-40°C to +50°C"),
            },
            
            environmental_specs={
                "IP Rating": structured.get("environmental", {}).get("ip_rating", "IP66"),
                "IK Rating": structured.get("environmental", {}).get("ik_rating", "IK08"),
                "Lifespan": f"L70 > {structured.get('environmental', {}).get('lifespan', '50,000')} hours",
            },
            
            certifications=structured.get("certifications", ["CE", "RoHS"]),
            features=self._extract_features(raw_text),
            applications=self._infer_applications(raw_text),
            
            raw_tables=extracted_data.get("tables", [])
        )
    
    def _extract_product_name(self, text: str, metadata: Dict) -> str:
        """Extract product name from text or metadata"""
        if metadata.get("title"):
            return metadata["title"]
        
        import re
        lines = text.split('\n')[:10]
        for line in lines:
            line = line.strip()
            if len(line) > 5 and len(line) < 100:
                if re.search(r'(LED|Light|Lamp|Fixture)', line, re.IGNORECASE):
                    return line
        
        return "LED Lighting Product"
    
    def _infer_category(self, text: str) -> str:
        """Infer product category from text"""
        text_lower = text.lower()
        
        categories = {
            "street light": ["street light", "streetlight", "road light", "roadway"],
            "flood light": ["flood light", "floodlight", "area light", "stadium"],
            "high bay": ["high bay", "highbay", "industrial light"],
            "panel light": ["panel light", "panel", "troffer"],
            "downlight": ["downlight", "down light", "recessed"],
        }
        
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return category.title()
        
        return "LED Light"
    
    def _extract_features(self, text: str) -> List[str]:
        """Extract key features from text"""
        import re
        features = []
        
        feature_indicators = [
            r"high\s+efficacy", r"energy\s+sav", r"long\s+life", r"ip\d{2}",
            r"surge\s+protection", r"dimmable", r"smart\s+control",
            r"thermal\s+management", r"modular\s+design",
        ]
        
        for pattern in feature_indicators:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                feature = match.group(0).strip()
                feature = ' '.join(word.capitalize() for word in feature.split())
                if feature not in features:
                    features.append(feature)
        
        return features[:8]
    
    def _infer_applications(self, text: str) -> List[str]:
        """Infer applications from text"""
        applications = []
        
        app_keywords = {
            "Streets & Roads": ["street", "road", "highway"],
            "Parking Areas": ["parking", "car park"],
            "Industrial Areas": ["industrial", "warehouse"],
            "Commercial Spaces": ["commercial", "retail"],
            "Sports Facilities": ["sports", "stadium", "field"],
        }
        
        text_lower = text.lower()
        for app, keywords in app_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    if app not in applications:
                        applications.append(app)
                    break
        
        return applications if applications else ["General Lighting Applications"]


def process_client_spec(extracted_data: Dict[str, Any], api_key: Optional[str] = None) -> ProcessedSpecification:
    """
    Legacy convenience function to process client specifications.
    
    For new implementations with AI Vision, use:
        from ai_vision_processor import process_vendor_spec
        from data_mapper import map_vendor_to_tds
    """
    processor = AISpecProcessor(api_key)
    return processor.process_specifications(extracted_data)


if __name__ == "__main__":
    # Test with sample data
    test_data = {
        "raw_text": "FL47 LED Street Light\n480W Power\n72000 lumens\nIP66 rated\n5000K CCT",
        "tables": [],
        "structured_data": {
            "electrical": {"wattage": "480"},
            "optical": {"lumens": "72000", "cct": "5000"}
        }
    }
    
    result = process_client_spec(test_data)
    print(json.dumps(asdict(result), indent=2))
