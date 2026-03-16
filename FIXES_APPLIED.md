# Fixes Applied for TDS Generator Issues

## Issues Fixed

### 1. **Standard Certification Badges Not Being Used**
**Problem**: Generated TDS was using extracted badges from vendor PDF instead of standard badges from `images` folder.

**Fix**:
- Modified `data_mapper.py` to ALWAYS use standard badges from Image Asset Manager
- Ensured certification badges are ONLY loaded from `images` folder, never from extracted vendor images
- Improved IP rating detection to match IP65/IK08 badges correctly
- Added automatic IP badge matching for IP65, IP66, IP67, IP68 ratings

### 2. **"Not Specified" Text Appearing in Generated TDS**
**Problem**: Fields showing "Not specified" instead of being empty.

**Fix**:
- Updated `_extract_spec_value()` in `data_mapper.py` to filter out "Not specified", "N/A", "NA", "-", "none"
- Updated `get_spec()` helper in `api.py` to filter out placeholder text
- Added `clean_value()` function in `pdf_generator.py` to clean dimension values
- Empty fields now show as blank instead of "Not specified"

### 3. **Empty Dimension Tables**
**Problem**: Dimension tables showing empty rows or "Not specified" values.

**Fix**:
- Improved dimension extraction to parse formats like "L x W x H" or "12.5\" x 8.5\" x 6.2\""
- Added individual dimension field extraction (Length, Width, Height, Wire Length)
- Filter out empty rows from dimension tables - only show rows with actual values
- Enhanced dimension parsing to handle various vendor formats

### 4. **Warranty Badge Not Matching**
**Problem**: Warranty badges not being matched correctly from warranty years.

**Fix**:
- Improved warranty year extraction using regex patterns
- Handles formats: "5 years", "5-year", "5yr", "5"
- Automatically matches to correct warranty badge (5-year or 10-year)
- Warranty badges are now included in certification badges list

### 5. **IP/IK Rating Badge Matching**
**Problem**: IP65 and IK08 badges not being matched from certifications.

**Fix**:
- Added IP rating regex matching to detect IP65, IP66, IP67, IP68
- Automatically adds IP65 badge when IP rating is detected
- Improved certification matching to handle various IP rating formats

## Code Changes Summary

### `data_mapper.py`
- Enhanced `_extract_spec_value()` to filter "Not specified" text
- Improved dimension extraction with regex parsing
- Fixed standard badge loading to ALWAYS use Image Asset Manager
- Added IP rating badge matching
- Improved warranty badge extraction

### `api.py`
- Updated `get_spec()` helper to filter placeholder text
- Enhanced dimension data extraction from TDS data

### `pdf_generator.py`
- Added `clean_value()` function to filter "Not specified" text
- Filter empty rows from dimension tables
- Only show dimension rows that have actual values

### `image_asset_manager.py`
- Fixed IP rating matching with regex
- Improved certification badge matching order
- Better handling of IP65/IK08 badges

## Testing Recommendations

1. **Test with vendor PDF that has IP65 rating** - Should show IP65 badge
2. **Test with warranty information** - Should show correct warranty badge (5-year or 10-year)
3. **Test with dimensions** - Should extract and display correctly, no "Not specified"
4. **Test with empty fields** - Should show blank, not "Not specified"
5. **Test certification matching** - Should use standard badges from images folder

## Expected Behavior After Fixes

✅ Standard certification badges ALWAYS used from `images` folder
✅ No "Not specified" text in generated TDS
✅ Empty fields show as blank
✅ Dimension tables only show rows with values
✅ IP65/IK08 badges matched correctly
✅ Warranty badges matched based on warranty years
✅ Better dimension extraction from various formats
