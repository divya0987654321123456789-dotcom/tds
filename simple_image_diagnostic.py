"""
Simple Image Diagnostic - No imports from project files
"""
import fitz
from PIL import Image
import io
import os

pdf_file = "Areon_AL_Bronze_70W100W150_MV_TDS.pdf"

if not os.path.exists(pdf_file):
    print(f"File not found: {pdf_file}")
    exit(1)

print(f"\n{'='*70}")
print(f"Analyzing: {pdf_file}")
print(f"{'='*70}\n")

doc = fitz.open(pdf_file)
print(f"Total pages: {len(doc)}\n")

os.makedirs("output/image_diagnostics", exist_ok=True)

total = 0
extracted = 0

for page_num in range(len(doc)):
    page = doc[page_num]
    images = page.get_images()
    
    if images:
        print(f"Page {page_num + 1}: {len(images)} images")
        
        for idx, img in enumerate(images):
            total += 1
            try:
                xref = img[0]
                base_img = doc.extract_image(xref)
                img_bytes = base_img["image"]
                ext = base_img["ext"]
                
                pil_img = Image.open(io.BytesIO(img_bytes))
                w, h = pil_img.size
                aspect = w / max(h, 1)
                
                # Classification
                if aspect > 2.0:
                    cls = "BEAM_PATTERN"
                elif 0.7 < aspect < 1.5 and w > 300:
                    cls = "DIMENSION"
                elif w < 200:
                    cls = "ACCESSORY"
                else:
                    cls = "PRODUCT"
                
                # Filter check
                if w >= 50 and h >= 50:
                    status = "✅"
                    extracted += 1
                    # Save image
                    filename = f"output/image_diagnostics/p{page_num+1}_i{idx+1}_{w}x{h}_{cls}.{ext}"
                    pil_img.save(filename)
                else:
                    status = "❌ FILTERED"
                    filename = "N/A"
                
                print(f"  {status} Img {idx+1}: {w}x{h} (AR={aspect:.2f}) -> {cls}")
                if status == "✅":
                    print(f"      Saved: {filename}")
                
            except Exception as e:
                print(f"  ❌ Error extracting image {idx+1}: {e}")

doc.close()

print(f"\n{'='*70}")
print(f"SUMMARY: {extracted}/{total} images extracted")
print(f"Images saved to: output/image_diagnostics/")
print(f"{'='*70}\n")
