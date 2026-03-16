"""
Test script to validate PDF generation improvements
"""
from data_mapper import IKIOTDSData, map_vendor_to_tds
from ai_vision_processor import VendorSpecData
from pdf_generator import generate_tds

# Create test vendor data with comprehensive specs
test_vendor_data = VendorSpecData(
    product_name="Test LED Area Light",
    product_category="LED AREA LUMINAIRE",
    product_description="High-performance LED area light designed for outdoor applications with superior durability and energy efficiency.",
    features=[
        "High efficacy LED technology",
        "Durable die-cast aluminum housing",
        "IP65 rated for outdoor use",
        "5-year warranty",
        "Easy installation"
    ],
    applications=["Parking Lots", "Streets", "Pathways"],
    model_numbers=["TEST-AL-100W-50K"],
    electrical_specs={
        "Power": "100W",
        "Voltage": "120-277V AC",
        "Power Factor": ">0.9",
        "THD": "<20%",
        "Current": "0.42A @ 277V"
    },
    optical_specs={
        "Lumens": "13000lm",
        "Efficacy": "130lm/W",
        "CCT": "5000K",
        "CRI": ">70",
        "Light Distribution": "Type III"
    },
    environmental_specs={
        "IP Rating": "IP65",
        "IK Rating": "IK08",
        "Operating Temperature": "-40°F to +122°F"
    },
    physical_specs={
        "Housing": "Die-cast Aluminum",
        "Lens": "Tempered Glass",
        "Finish": "Bronze",
        "Dimensions": "15\" x 12\" x 6\"",
        "Weight": "12 lbs"
    },
    lifespan_specs={
        "Lifespan": "50,000 hours (L70)",
        "Warranty": "5 Years"
    },
    component_specs={
        "LED Source": "Lumileds 3030",
        "Power Supply": "Meanwell Driver"
    },
    certifications=["cETLus", "DLC Premium"],
    images=[]
)

print("=" * 60)
print("Testing Data Mapper Enhancements")
print("=" * 60)

# Map vendor data to TDS format
tds_data = map_vendor_to_tds(test_vendor_data)

# Validate that all critical fields are populated
critical_fields = [
    'product_name', 'product_category', 'product_description',
    'wattage', 'input_voltage', 'lumens', 'efficacy', 'cct', 'cri',
    'ip_rating', 'housing_material', 'lens_material'
]

print("\nValidating critical fields:")
missing_fields = []
populated_fields = []

for field in critical_fields:
    value = getattr(tds_data, field, "")
    if value and str(value).strip():
        populated_fields.append(field)
        print(f"  ✓ {field}: {value}")
    else:
        missing_fields.append(field)
        print(f"  ✗ {field}: MISSING")

print(f"\nResults:")
print(f"  Populated: {len(populated_fields)}/{len(critical_fields)}")
print(f"  Missing: {len(missing_fields)}/{len(critical_fields)}")

if missing_fields:
    print(f"\n⚠ WARNING: Missing fields: {', '.join(missing_fields)}")
else:
    print(f"\n✓ SUCCESS: All critical fields populated!")

print("\n" + "=" * 60)
print("Testing PDF Generation")
print("=" * 60)

try:
    output_path = "output/TEST_validation_output.pdf"
    result = generate_tds(tds_data, output_path, open_after=False)
    print(f"\n✓ PDF generated successfully: {result}")
    print("\nPlease review the generated PDF to verify:")
    print("  1. No blank spaces in required fields")
    print("  2. All text is visible (no clipping)")
    print("  3. Proper alignment and formatting")
    print("  4. Correct IKIO green color (#3fad42)")
except Exception as e:
    print(f"\n✗ PDF generation failed: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
