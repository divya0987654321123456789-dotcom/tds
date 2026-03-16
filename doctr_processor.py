"""
DocTR-based Document Processor for Vendor Spec Sheet Extraction
Uses deep learning (docTR) for accurate OCR, layout analysis, and table detection
Combined with AI for semantic understanding
"""
import io
import re
import json
import base64
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from PIL import Image
import numpy as np
import fitz  # PyMuPDF
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

# DocTR imports
try:
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor
    DOCTR_AVAILABLE = True
except ImportError:
    DOCTR_AVAILABLE = False
    print("Warning: docTR not installed. Run: pip install python-doctr[torch]")

# PaddleOCR as fallback
try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False

from config import TEMP_DIR

console = Console()


@dataclass
class TextBlock:
    """Represents a detected text block with position"""
    text: str
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    page: int
    block_type: str = "text"  # text, header, table_cell, list_item


@dataclass
class DetectedTable:
    """Represents a detected table structure"""
    page: int
    x1: float
    y1: float
    x2: float
    y2: float
    headers: List[str]
    rows: List[List[str]]
    title: str = ""


@dataclass
class DetectedImage:
    """Represents a detected image/diagram region"""
    page: int
    x1: float
    y1: float
    x2: float
    y2: float
    image_data: bytes
    image_type: str  # product, dimension, beam_pattern, wiring, mounting
    width: int
    height: int


@dataclass
class DocumentLayout:
    """Complete document layout analysis"""
    text_blocks: List[TextBlock] = field(default_factory=list)
    tables: List[DetectedTable] = field(default_factory=list)
    images: List[DetectedImage] = field(default_factory=list)
    sections: Dict[str, List[TextBlock]] = field(default_factory=dict)
    page_count: int = 0
    full_text: str = ""


class DocTRProcessor:
    """
    Deep learning-based document processor using docTR
    Provides accurate OCR, layout detection, and table extraction
    """
    
    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu
        self.ocr_model = None
        self.paddle_ocr = None
        
        # Initialize OCR engine
        self._initialize_ocr()
        
        # Section header patterns for spec sheets
        self.section_patterns = {
            'features': r'(?i)(key\s*)?features?|highlights?',
            'specifications': r'(?i)specifications?|technical\s*data|specs',
            'electrical': r'(?i)electrical\s*(specifications?)?|power\s*specs?',
            'optical': r'(?i)optical\s*(specifications?)?|light\s*output|photometric',
            'physical': r'(?i)physical\s*(specifications?)?|dimensions?|mechanical',
            'environmental': r'(?i)environmental|ratings?|ip\s*rating|operating\s*conditions?',
            'applications': r'(?i)applications?|application\s*areas?|suitable\s*for|use\s*cases?',
            'ordering': r'(?i)ordering\s*(information|guide|codes?)?|part\s*numbers?|model\s*numbers?',
            'accessories': r'(?i)accessories|optional|mounting\s*options?',
            'warranty': r'(?i)warranty|guarantee',
            'certifications': r'(?i)certifications?|approvals?|listings?|compliance',
            'dimensions': r'(?i)dimensions?|size|measurements?',
        }
        
        # Specification key patterns
        self.spec_patterns = {
            # Electrical
            'wattage': r'(?i)(power|wattage|watts?)\s*[:\-]?\s*([\d\.\-\/\s]+\s*W)',
            'voltage': r'(?i)(input\s*)?voltage\s*[:\-]?\s*([\d\.\-]+\s*V?(?:\s*AC|\s*DC)?)',
            'power_factor': r'(?i)power\s*factor\s*[:\-]?\s*([\d\.>]+)',
            'frequency': r'(?i)frequency\s*[:\-]?\s*([\d\/]+\s*Hz)',
            
            # Optical
            'lumens': r'(?i)(lumens?|luminous\s*flux)\s*[:\-]?\s*([\d,\.]+\s*(?:lm)?)',
            'efficacy': r'(?i)(efficacy|efficiency)\s*[:\-]?\s*([\d\.]+\s*(?:lm\/W|lm/W)?)',
            'cct': r'(?i)(cct|color\s*temp(?:erature)?)\s*[:\-]?\s*([\d,\/\s]+\s*K)',
            'cri': r'(?i)(cri|color\s*rendering)\s*[:\-]?\s*([>]?[\d\.]+)',
            'beam_angle': r'(?i)beam\s*angle\s*[:\-]?\s*([\d\.°\-x×]+)',
            
            # Physical
            'dimensions': r'(?i)dimensions?\s*[:\-]?\s*([\d\.\s×xX\-]+\s*(?:mm|cm|in)?)',
            'weight': r'(?i)(net\s*)?weight\s*[:\-]?\s*([\d\.]+\s*(?:kg|g|lbs?|oz)?)',
            'housing': r'(?i)housing\s*(?:material)?\s*[:\-]?\s*([A-Za-z\s\-]+)',
            
            # Environmental
            'ip_rating': r'(?i)ip\s*(?:rating)?\s*[:\-]?\s*(IP\s*\d+)',
            'ik_rating': r'(?i)ik\s*(?:rating)?\s*[:\-]?\s*(IK\s*\d+)',
            'operating_temp': r'(?i)operating\s*temp(?:erature)?\s*[:\-]?\s*([\-\d]+\s*[°]?\s*C?\s*(?:to|~|\-)\s*[\+\-]?\d+\s*[°]?\s*C?)',
            
            # Lifespan
            'lifespan': r'(?i)(lifespan|life|l70|average\s*life)\s*[:\-]?\s*([\d,\.]+\s*(?:hours?|hrs?)?)',
            'warranty': r'(?i)warranty\s*[:\-]?\s*([\d]+\s*(?:years?|yrs?))',
        }
    
    def _initialize_ocr(self):
        """Initialize the OCR engine (docTR or PaddleOCR)"""
        if DOCTR_AVAILABLE:
            try:
                console.print("[cyan]Initializing docTR OCR engine...[/cyan]")
                # Use detection + recognition predictor
                self.ocr_model = ocr_predictor(
                    det_arch='db_resnet50',  # Text detection
                    reco_arch='crnn_vgg16_bn',  # Text recognition
                    pretrained=True
                )
                console.print("[green]✓ docTR OCR engine ready[/green]")
                return
            except Exception as e:
                console.print(f"[yellow]Warning: docTR initialization failed: {e}[/yellow]")
        
        if PADDLE_AVAILABLE:
            try:
                console.print("[cyan]Initializing PaddleOCR engine...[/cyan]")
                self.paddle_ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang='en',
                    use_gpu=self.use_gpu,
                    show_log=False
                )
                console.print("[green]✓ PaddleOCR engine ready[/green]")
                return
            except Exception as e:
                console.print(f"[yellow]Warning: PaddleOCR initialization failed: {e}[/yellow]")
        
        console.print("[yellow]Warning: No deep learning OCR available. Using PyMuPDF text extraction.[/yellow]")
    
    def process_document(self, pdf_path: str) -> DocumentLayout:
        """
        Process a PDF document and extract complete layout information
        """
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        console.print(f"[cyan]Processing document: {pdf_path_obj.name}[/cyan]")
        
        layout = DocumentLayout()
        
        # Open PDF with PyMuPDF
        doc = fitz.open(pdf_path)
        layout.page_count = len(doc)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            # Step 1: Extract text using deep learning OCR
            task1 = progress.add_task("Extracting text with OCR...", total=layout.page_count)
            layout.text_blocks = self._extract_text_blocks(doc, progress, task1)
            
            # Step 2: Extract and classify images
            task2 = progress.add_task("Extracting images...", total=layout.page_count)
            layout.images = self._extract_images(doc, progress, task2)
            
            # Step 3: Detect tables
            task3 = progress.add_task("Detecting tables...", total=1)
            layout.tables = self._detect_tables(layout.text_blocks)
            progress.update(task3, completed=1)
            
            # Step 4: Identify sections
            task4 = progress.add_task("Identifying sections...", total=1)
            layout.sections = self._identify_sections(layout.text_blocks)
            progress.update(task4, completed=1)
            
            # Step 5: Build full text
            layout.full_text = self._build_full_text(layout.text_blocks)
        
        doc.close()
        
        console.print(f"[green]✓ Extracted {len(layout.text_blocks)} text blocks, "
                     f"{len(layout.tables)} tables, {len(layout.images)} images[/green]")
        
        return layout
    
    def _extract_text_blocks(self, doc: fitz.Document, progress, task) -> List[TextBlock]:
        """Extract text blocks with positions using deep learning OCR"""
        all_blocks = []
        
        for page_num in range(len(doc)):
            progress.update(task, description=f"OCR page {page_num + 1}...")
            page = doc[page_num]
            
            if self.ocr_model:
                # Use docTR
                blocks = self._doctr_extract_page(page, page_num)
            elif self.paddle_ocr:
                # Use PaddleOCR
                blocks = self._paddle_extract_page(page, page_num)
            else:
                # Fallback to PyMuPDF text extraction
                blocks = self._pymupdf_extract_page(page, page_num)
            
            all_blocks.extend(blocks)
            progress.advance(task)
        
        return all_blocks
    
    def _doctr_extract_page(self, page: fitz.Page, page_num: int) -> List[TextBlock]:
        """Extract text using docTR"""
        import tempfile
        import os
        
        blocks = []
        
        # Render page to image
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
        pix = page.get_pixmap(matrix=mat)
        
        # Save to temp file - docTR works best with file paths
        temp_img_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp.write(pix.tobytes("png"))
                temp_img_path = tmp.name
            
            # Load document from file path
            doc = DocumentFile.from_images([temp_img_path])
            result = self.ocr_model(doc)
            
            # Extract text blocks with positions
            page_width, page_height = page.rect.width, page.rect.height
            
            for page_result in result.pages:
                for block in page_result.blocks:
                    for line in block.lines:
                        text = " ".join([word.value for word in line.words])
                        if not text.strip():
                            continue
                        
                        # Get bounding box (normalized coordinates)
                        geo = line.geometry
                        x1 = geo[0][0] * page_width
                        y1 = geo[0][1] * page_height
                        x2 = geo[1][0] * page_width
                        y2 = geo[1][1] * page_height
                        
                        # Calculate confidence
                        confidence = np.mean([word.confidence for word in line.words])
                        
                        blocks.append(TextBlock(
                            text=text,
                            x1=x1, y1=y1, x2=x2, y2=y2,
                            confidence=float(confidence),
                            page=page_num + 1,
                            block_type=self._classify_text_block(text)
                        ))
        finally:
            # Clean up temp file
            if temp_img_path and os.path.exists(temp_img_path):
                try:
                    os.unlink(temp_img_path)
                except:
                    pass
        
        return blocks
    
    def _paddle_extract_page(self, page: fitz.Page, page_num: int) -> List[TextBlock]:
        """Extract text using PaddleOCR"""
        blocks = []
        
        # Render page to image
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        
        img = Image.open(io.BytesIO(img_bytes))
        img_array = np.array(img)
        
        # Run OCR
        result = self.paddle_ocr.ocr(img_array, cls=True)
        
        page_width, page_height = page.rect.width, page.rect.height
        scale = 2.0  # Account for zoom
        
        if result and result[0]:
            for line in result[0]:
                bbox = line[0]
                text = line[1][0]
                confidence = line[1][1]
                
                if not text.strip():
                    continue
                
                # Convert coordinates back to page space
                x1 = min(p[0] for p in bbox) / scale
                y1 = min(p[1] for p in bbox) / scale
                x2 = max(p[0] for p in bbox) / scale
                y2 = max(p[1] for p in bbox) / scale
                
                blocks.append(TextBlock(
                    text=text,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    confidence=confidence,
                    page=page_num + 1,
                    block_type=self._classify_text_block(text)
                ))
        
        return blocks
    
    def _pymupdf_extract_page(self, page: fitz.Page, page_num: int) -> List[TextBlock]:
        """Fallback text extraction using PyMuPDF"""
        blocks = []
        
        # Get text blocks with positions
        text_dict = page.get_text("dict")
        
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # Skip non-text blocks
                continue
            
            for line in block.get("lines", []):
                text = " ".join([span.get("text", "") for span in line.get("spans", [])])
                if not text.strip():
                    continue
                
                bbox = line.get("bbox", [0, 0, 0, 0])
                
                blocks.append(TextBlock(
                    text=text.strip(),
                    x1=bbox[0], y1=bbox[1], x2=bbox[2], y2=bbox[3],
                    confidence=0.9,  # PyMuPDF has high accuracy for digital PDFs
                    page=page_num + 1,
                    block_type=self._classify_text_block(text)
                ))
        
        return blocks
    
    def _classify_text_block(self, text: str) -> str:
        """Classify text block type"""
        text_lower = text.lower().strip()
        
        # Check if it's a header
        for pattern in self.section_patterns.values():
            if re.search(pattern, text_lower):
                return "header"
        
        # Check if it's a list item
        if text.startswith(('•', '-', '●', '○', '◦', '*', '✓', '✔')):
            return "list_item"
        
        # Check if it looks like a spec value
        if ':' in text or any(re.search(p, text) for p in self.spec_patterns.values()):
            return "spec_value"
        
        return "text"
    
    def _extract_images(self, doc: fitz.Document, progress, task) -> List[DetectedImage]:
        """Extract all images from PDF with classification"""
        images = []
        
        for page_num in range(len(doc)):
            progress.update(task, description=f"Extracting images from page {page_num + 1}...")
            page = doc[page_num]
            image_list = page.get_images()
            
            for img in image_list:
                try:
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    
                    # Get image dimensions
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    width, height = pil_image.size
                    
                    # Skip tiny icons
                    if width < 50 or height < 50:
                        continue
                    
                    # Classify image type based on characteristics
                    image_type = self._classify_image(pil_image, width, height)
                    
                    # Get approximate position on page (if available)
                    x1, y1, x2, y2 = 0, 0, width, height
                    
                    images.append(DetectedImage(
                        page=page_num + 1,
                        x1=x1, y1=y1, x2=x2, y2=y2,
                        image_data=image_bytes,
                        image_type=image_type,
                        width=width,
                        height=height
                    ))
                    
                except Exception as e:
                    continue
            
            progress.advance(task)
        
        return images
    
    def _classify_image(self, img: Image.Image, width: int, height: int) -> str:
        """Classify image type based on visual characteristics"""
        aspect_ratio = width / max(height, 1)
        
        # Convert to grayscale for analysis
        gray = img.convert('L')
        img_array = np.array(gray)
        
        # Calculate statistics
        mean_val = np.mean(img_array)
        std_val = np.std(img_array)
        
        # Wide images with high contrast are often beam angle diagrams
        if aspect_ratio > 2.0 and std_val > 50:
            return "beam_pattern"
        
        # Images with lots of lines (high edge content) are often dimension diagrams
        # Simple edge detection using gradient
        gradient = np.abs(np.diff(img_array.astype(float), axis=0)).mean()
        if gradient > 20 and 0.5 < aspect_ratio < 2.0 and width > 200:
            return "dimension"
        
        # Square-ish images with moderate contrast are likely product images
        if 0.7 < aspect_ratio < 1.5 and width > 150:
            return "product"
        
        # Small images are likely accessories or icons
        if width < 200 or height < 200:
            return "accessory"
        
        return "product"
    
    def _detect_tables(self, text_blocks: List[TextBlock]) -> List[DetectedTable]:
        """Detect tables based on text block alignment"""
        tables = []
        
        # Group blocks by page
        blocks_by_page = {}
        for block in text_blocks:
            if block.page not in blocks_by_page:
                blocks_by_page[block.page] = []
            blocks_by_page[block.page].append(block)
        
        for page_num, page_blocks in blocks_by_page.items():
            # Sort by y position
            page_blocks.sort(key=lambda b: (b.y1, b.x1))
            
            # Find potential table regions (aligned text blocks)
            table_candidates = self._find_aligned_blocks(page_blocks)
            
            for candidate in table_candidates:
                if len(candidate) >= 2:  # At least 2 rows
                    table = self._blocks_to_table(candidate, page_num)
                    if table:
                        tables.append(table)
        
        return tables
    
    def _find_aligned_blocks(self, blocks: List[TextBlock]) -> List[List[TextBlock]]:
        """Find groups of horizontally aligned blocks (potential table rows)"""
        if not blocks:
            return []
        
        # Group blocks that are on the same horizontal line (similar y)
        rows = []
        current_row = [blocks[0]]
        
        for block in blocks[1:]:
            # Check if this block is on the same row (similar y coordinate)
            if abs(block.y1 - current_row[0].y1) < 15:  # 15pt tolerance
                current_row.append(block)
            else:
                if len(current_row) >= 2:  # At least 2 columns to be a table row
                    rows.append(sorted(current_row, key=lambda b: b.x1))
                current_row = [block]
        
        if len(current_row) >= 2:
            rows.append(sorted(current_row, key=lambda b: b.x1))
        
        # Group consecutive rows into tables
        tables = []
        current_table = []
        
        for i, row in enumerate(rows):
            if not current_table:
                current_table.append(row)
            else:
                # Check if this row has similar structure to previous
                prev_row = current_table[-1]
                if abs(len(row) - len(prev_row)) <= 1:  # Similar column count
                    current_table.append(row)
                else:
                    if len(current_table) >= 2:
                        tables.append(current_table)
                    current_table = [row]
        
        if len(current_table) >= 2:
            tables.append(current_table)
        
        return tables
    
    def _blocks_to_table(self, block_rows: List[List[TextBlock]], page_num: int) -> Optional[DetectedTable]:
        """Convert aligned text blocks to table structure"""
        if len(block_rows) < 2:
            return None
        
        # First row is typically header
        headers = [b.text for b in block_rows[0]]
        rows = [[b.text for b in row] for row in block_rows[1:]]
        
        # Get bounding box
        all_blocks = [b for row in block_rows for b in row]
        x1 = min(b.x1 for b in all_blocks)
        y1 = min(b.y1 for b in all_blocks)
        x2 = max(b.x2 for b in all_blocks)
        y2 = max(b.y2 for b in all_blocks)
        
        # Try to find table title (text block just above the table)
        title = ""
        
        return DetectedTable(
            page=page_num,
            x1=x1, y1=y1, x2=x2, y2=y2,
            headers=headers,
            rows=rows,
            title=title
        )
    
    def _identify_sections(self, text_blocks: List[TextBlock]) -> Dict[str, List[TextBlock]]:
        """Identify document sections based on headers"""
        sections = {name: [] for name in self.section_patterns.keys()}
        current_section = None
        
        for block in text_blocks:
            # Check if this block is a section header
            for section_name, pattern in self.section_patterns.items():
                if re.search(pattern, block.text, re.IGNORECASE):
                    current_section = section_name
                    break
            
            # Add block to current section
            if current_section:
                sections[current_section].append(block)
        
        # Remove empty sections
        return {k: v for k, v in sections.items() if v}
    
    def _build_full_text(self, text_blocks: List[TextBlock]) -> str:
        """Build full text from text blocks in reading order"""
        # Sort blocks by page, then y, then x
        sorted_blocks = sorted(text_blocks, key=lambda b: (b.page, b.y1, b.x1))
        
        lines = []
        current_line = []
        current_y = None
        
        for block in sorted_blocks:
            if current_y is None or abs(block.y1 - current_y) < 10:
                current_line.append(block.text)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [block.text]
            current_y = block.y1
        
        if current_line:
            lines.append(" ".join(current_line))
        
        return "\n".join(lines)
    
    def extract_specifications(self, layout: DocumentLayout) -> Dict[str, Any]:
        """Extract structured specifications from document layout"""
        specs = {
            'electrical': {},
            'optical': {},
            'physical': {},
            'environmental': {},
            'lifespan': {}
        }
        
        full_text = layout.full_text
        
        # Extract using regex patterns
        for spec_key, pattern in self.spec_patterns.items():
            match = re.search(pattern, full_text)
            if match:
                value = match.group(2) if len(match.groups()) > 1 else match.group(1)
                value = value.strip()
                
                # Categorize specification
                if spec_key in ['wattage', 'voltage', 'power_factor', 'frequency']:
                    specs['electrical'][spec_key] = value
                elif spec_key in ['lumens', 'efficacy', 'cct', 'cri', 'beam_angle']:
                    specs['optical'][spec_key] = value
                elif spec_key in ['dimensions', 'weight', 'housing']:
                    specs['physical'][spec_key] = value
                elif spec_key in ['ip_rating', 'ik_rating', 'operating_temp']:
                    specs['environmental'][spec_key] = value
                elif spec_key in ['lifespan', 'warranty']:
                    specs['lifespan'][spec_key] = value
        
        # Also extract from detected tables
        for table in layout.tables:
            self._extract_specs_from_table(table, specs)
        
        return specs
    
    def _extract_specs_from_table(self, table: DetectedTable, specs: Dict):
        """Extract specifications from a detected table"""
        for row in table.rows:
            if len(row) >= 2:
                key = row[0].lower().strip()
                value = row[1].strip()
                
                # Categorize based on key
                if any(x in key for x in ['power', 'voltage', 'watt', 'current']):
                    specs['electrical'][key] = value
                elif any(x in key for x in ['lumen', 'efficacy', 'cct', 'cri', 'beam']):
                    specs['optical'][key] = value
                elif any(x in key for x in ['dimension', 'weight', 'size', 'material']):
                    specs['physical'][key] = value
                elif any(x in key for x in ['ip', 'ik', 'temp', 'humidity']):
                    specs['environmental'][key] = value
                elif any(x in key for x in ['life', 'warranty', 'hours']):
                    specs['lifespan'][key] = value
    
    def extract_features_applications(self, layout: DocumentLayout) -> Tuple[List[str], List[str]]:
        """Extract features and applications lists"""
        features = []
        applications = []
        
        # Get from identified sections
        if 'features' in layout.sections:
            for block in layout.sections['features']:
                if block.block_type == 'list_item' or block.text.startswith(('•', '-', '●')):
                    feature = re.sub(r'^[•\-●○◦\*✓✔]\s*', '', block.text).strip()
                    if feature and len(feature) > 5:
                        features.append(feature)
        
        if 'applications' in layout.sections:
            for block in layout.sections['applications']:
                if block.block_type == 'list_item' or block.text.startswith(('•', '-', '●')):
                    app = re.sub(r'^[•\-●○◦\*✓✔]\s*', '', block.text).strip()
                    if app and len(app) > 3:
                        applications.append(app)
        
        # Also search full text for common patterns
        if not features:
            feature_matches = re.findall(r'[•\-●]\s*([A-Z][^•\-●\n]{10,})', layout.full_text)
            features = [f.strip() for f in feature_matches[:10]]
        
        return features, applications


def create_doctr_processor(use_gpu: bool = False) -> DocTRProcessor:
    """Factory function to create DocTR processor"""
    return DocTRProcessor(use_gpu=use_gpu)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        processor = DocTRProcessor()
        layout = processor.process_document(sys.argv[1])
        
        print(f"\n=== Document Analysis ===")
        print(f"Pages: {layout.page_count}")
        print(f"Text blocks: {len(layout.text_blocks)}")
        print(f"Tables: {len(layout.tables)}")
        print(f"Images: {len(layout.images)}")
        print(f"Sections: {list(layout.sections.keys())}")
        
        specs = processor.extract_specifications(layout)
        print(f"\n=== Extracted Specifications ===")
        print(json.dumps(specs, indent=2))
    else:
        print("Usage: python doctr_processor.py <spec_sheet.pdf>")

