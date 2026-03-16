"""
Image Extraction Diagnostic Tool
Analyzes vendor PDFs to show what images are extracted and why some might be missing
"""
import fitz
from PIL import Image
import io
import os
from pathlib import Path

def diagnose_pdf_images(pdf_path: str, output_dir: str = "output/image_diagnostics"):
    """
    Extract and save all images from a PDF with diagnostic information.
    Creates snapshots of each image with metadata.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"❌ PDF not found: {pdf_path}")
        return
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Create subfolder for this PDF
    pdf_folder = output_path / pdf_path.stem
    pdf_folder.mkdir(exist_ok=True)
    
    print(f"\n{'='*70}")
    print(f"📄 Analyzing: {pdf_path.name}")
    print(f"{'='*70}\n")
    
    doc = fitz.open(pdf_path)
    total_images = 0
    extracted_images = 0
    filtered_images = 0
    
    diagnostic_report = []
    diagnostic_report.append(f"PDF Image Extraction Diagnostic Report")
    diagnostic_report.append(f"PDF: {pdf_path.name}")
    diagnostic_report.append(f"Pages: {len(doc)}")
    diagnostic_report.append(f"\n{'='*70}\n")
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images()
        
        if image_list:
            print(f"\n📃 Page {page_num + 1}: Found {len(image_list)} images")
            diagnostic_report.append(f"\nPage {page_num + 1}: {len(image_list)} images")
            diagnostic_report.append("-" * 70)
        
        for img_index, img in enumerate(image_list):
            total_images += 1
            try:
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                ext = base_image["ext"]
                
                # Get image dimensions
                pil_image = Image.open(io.BytesIO(image_bytes))
                width, height = pil_image.size
                aspect_ratio = width / max(height, 1)
                
                # Determine if this would be filtered
                min_size = 50
                would_be_filtered = width < min_size or height < min_size
                
                # Classify based on current logic
                classification = "UNKNOWN"
                if aspect_ratio > 2.0:
                    classification = "BEAM_PATTERN (aspect > 2.0)"
                elif 0.7 < aspect_ratio < 1.5 and width > 300:
                    classification = "DIMENSION (square-ish, width > 300)"
                elif width < 200:
                    classification = "ACCESSORY (width < 200)"
                else:
                    classification = "PRODUCT (default)"
                
                # Determine extraction status
                if would_be_filtered:
                    status = "❌ FILTERED OUT"
                    filtered_images += 1
                else:
                    status = "✅ EXTRACTED"
                    extracted_images += 1
                
                # Save image snapshot
                img_filename = f"page{page_num+1}_img{img_index+1}_{width}x{height}.{ext}"
                img_path = pdf_folder / img_filename
                pil_image.save(img_path)
                
                # Print diagnostic info
                print(f"  {status} Image {img_index + 1}:")
                print(f"    Size: {width}x{height} px")
                print(f"    Aspect Ratio: {aspect_ratio:.2f}")
                print(f"    Classification: {classification}")
                print(f"    Saved as: {img_filename}")
                
                # Add to report
                diagnostic_report.append(f"\n  Image {img_index + 1}: {status}")
                diagnostic_report.append(f"    Dimensions: {width} x {height} px")
                diagnostic_report.append(f"    Aspect Ratio: {aspect_ratio:.2f}")
                diagnostic_report.append(f"    File Size: {len(image_bytes):,} bytes")
                diagnostic_report.append(f"    Classification: {classification}")
                diagnostic_report.append(f"    Saved: {img_filename}")
                
                if would_be_filtered:
                    diagnostic_report.append(f"    ⚠️  REASON FOR FILTERING: Image too small (< {min_size}x{min_size})")
                
            except Exception as e:
                print(f"  ❌ Failed to extract image {img_index + 1}: {e}")
                diagnostic_report.append(f"\n  Image {img_index + 1}: ❌ EXTRACTION FAILED")
                diagnostic_report.append(f"    Error: {str(e)}")
    
    doc.close()
    
    # Summary
    print(f"\n{'='*70}")
    print(f"📊 SUMMARY")
    print(f"{'='*70}")
    print(f"Total images found: {total_images}")
    print(f"Successfully extracted: {extracted_images}")
    print(f"Filtered out (too small): {filtered_images}")
    print(f"\n✅ All images saved to: {pdf_folder}")
    
    diagnostic_report.append(f"\n{'='*70}")
    diagnostic_report.append(f"SUMMARY")
    diagnostic_report.append(f"{'='*70}")
    diagnostic_report.append(f"Total images found: {total_images}")
    diagnostic_report.append(f"Successfully extracted: {extracted_images}")
    diagnostic_report.append(f"Filtered out: {filtered_images}")
    
    # Save diagnostic report
    report_path = pdf_folder / "diagnostic_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(diagnostic_report))
    
    print(f"📄 Diagnostic report saved: {report_path}\n")
    
    return {
        "total": total_images,
        "extracted": extracted_images,
        "filtered": filtered_images,
        "output_folder": str(pdf_folder)
    }


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        pdf_file = sys.argv[1]
    else:
        # Default: analyze a sample vendor PDF
        vendor_pdfs = [
            "Areon_AL_Bronze_70W100W150_MV_TDS.pdf",
            "FL47_specifications_V3.1[1].pdf",
            "3inch Downlight.pdf"
        ]
        
        print("Available vendor PDFs:")
        for i, pdf in enumerate(vendor_pdfs, 1):
            if os.path.exists(pdf):
                print(f"  {i}. {pdf}")
        
        choice = input("\nEnter number to analyze (or path to PDF): ").strip()
        
        if choice.isdigit() and 1 <= int(choice) <= len(vendor_pdfs):
            pdf_file = vendor_pdfs[int(choice) - 1]
        else:
            pdf_file = choice
    
    if os.path.exists(pdf_file):
        result = diagnose_pdf_images(pdf_file)
        print(f"\n🎯 Next Steps:")
        print(f"1. Review extracted images in: {result['output_folder']}")
        print(f"2. Check diagnostic_report.txt for details")
        print(f"3. Identify which images should be classified as photometric/dimension diagrams")
    else:
        print(f"❌ File not found: {pdf_file}")
        print(f"\nUsage: python diagnose_images.py <path_to_pdf>")
