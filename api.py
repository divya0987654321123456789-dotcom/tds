"""
Flask REST API for TDS Generator
Provides endpoints for file upload, processing, and PDF generation
"""
import sys
import io

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import tempfile
import os
import base64
import re
from pathlib import Path
from datetime import datetime
import json
import traceback

# Import existing modules
from ai_vision_processor import process_vendor_spec, VendorSpecData
from data_mapper import map_vendor_to_tds, IKIOTDSData
from pdf_generator import generate_tds
from product_knowledge import (
    get_profile_badge_terms,
    get_profile_header,
    get_profile_warranty,
    match_product_profile,
)
from config import (
    OUTPUT_DIR, AI_PROVIDER, 
    GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY,
    get_active_provider_info
)

# Try to import enhanced processor
try:
    from enhanced_processor import process_enhanced
    ENHANCED_AVAILABLE = True
except ImportError:
    process_enhanced = None
    ENHANCED_AVAILABLE = False

# Import AI content enhancer
try:
    from ai_enhancer import enhance_vendor_data
    AI_ENHANCER_AVAILABLE = True
except ImportError:
    enhance_vendor_data = None
    AI_ENHANCER_AVAILABLE = False

# Import image asset manager
try:
    from image_asset_manager import get_asset_manager
    IMAGE_ASSET_MANAGER_AVAILABLE = True
except ImportError:
    get_asset_manager = None
    IMAGE_ASSET_MANAGER_AVAILABLE = False

try:
    from ai_client import get_ai_client
    AI_CLIENT_AVAILABLE = True
except ImportError:
    get_ai_client = None
    AI_CLIENT_AVAILABLE = False

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])

# Store extracted data for review
extracted_sessions = {}

PAGE_COPY_LIMITS = {
    "description_words": 34,
    "application_words": 10,
    "feature_words": 6,
    "feature_count": 5,
}


def _clean_value(value):
    """Normalize empty placeholders to blank strings."""
    if value is None:
        return ""
    result = str(value).strip()
    if result.lower() in {"not specified", "n/a", "na", "-", "none", "null"}:
        return ""
    return result


def _normalize_whitespace(value):
    return re.sub(r"\s+", " ", _clean_value(value)).strip()


def _limit_words(value, max_words):
    text = _normalize_whitespace(value)
    if not text or max_words <= 0:
        return ""
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(",;:-") + "..."


def _dedupe_preserve_order(items):
    seen = set()
    result = []
    for item in items:
        cleaned = _normalize_whitespace(item)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _spec_fragment(specs, *keys, prefix=""):
    value = _get_spec_value(specs, *keys)
    if not value:
        return ""
    return f"{prefix}{value}".strip()


def _rewrite_application_text(application_text, category):
    raw = _normalize_whitespace(application_text)
    if not raw:
        fallback = f"{category} projects" if category else "general lighting projects"
        return _limit_words(fallback, PAGE_COPY_LIMITS["application_words"])
    compact = raw.replace("/", ", ").replace("|", ", ")
    parts = [part.strip(" .;:,-") for part in re.split(r",|;|\band\b", compact) if part.strip(" .;:,-")]
    if not parts:
        return _limit_words(raw, PAGE_COPY_LIMITS["application_words"])
    return _limit_words(", ".join(parts[:3]), PAGE_COPY_LIMITS["application_words"])


def _rewrite_feature_text(feature, specs):
    text = _normalize_whitespace(feature)
    lowered = text.lower()

    ip_match = re.search(r"\bip\s*([0-9]{2})\b", lowered)
    if ip_match:
        return f"IP{ip_match.group(1)} weather protection"

    ik_match = re.search(r"\bik\s*([0-9]{2})\b", lowered)
    if ik_match:
        return f"IK{ik_match.group(1)} impact resistance"

    if "cct" in lowered or "color temperature" in lowered:
        cct_value = _get_spec_value(specs, "cct", "color temp", "kelvin")
        return _limit_words(f"Selectable CCT {cct_value}" if cct_value else "Selectable CCT options", PAGE_COPY_LIMITS["feature_words"])

    if "dimm" in lowered:
        return "Dimming control support"

    if "sensor" in lowered or "motion" in lowered:
        return "Sensor-ready control support"

    if "effic" in lowered or "lm/w" in lowered:
        efficacy = _get_spec_value(specs, "efficacy", "lm/w")
        return _limit_words(f"High efficacy {efficacy}" if efficacy else "High efficacy output", PAGE_COPY_LIMITS["feature_words"])

    if "voltage" in lowered:
        voltage = _get_spec_value(specs, "voltage", "input voltage")
        return _limit_words(f"Wide voltage input {voltage}" if voltage else "Wide voltage input", PAGE_COPY_LIMITS["feature_words"])

    if "warranty" in lowered:
        return "Long-life warranty coverage"

    if "aluminum" in lowered or "die-cast" in lowered:
        return "Die-cast aluminum housing"

    cleaned = re.sub(r"^[\-\u2022\s]+", "", text)
    cleaned = re.sub(r"\b(the|and|with|for|that|this|from|designed|engineered|ideal|advanced|premium|superior)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = _normalize_whitespace(cleaned)
    return _limit_words(cleaned, PAGE_COPY_LIMITS["feature_words"])


def _polish_features_for_layout(features, specs):
    candidates = _dedupe_preserve_order(features or [])
    polished = []
    for item in candidates:
        rewritten = _rewrite_feature_text(item, specs)
        if rewritten:
            polished.append(rewritten)
    polished = _dedupe_preserve_order(polished)
    return polished[:PAGE_COPY_LIMITS["feature_count"]]


def _polish_description_for_layout(product_name, category, features, specs, application_text):
    name = _normalize_whitespace(product_name) or "This fixture"
    category_value = _normalize_whitespace(category).lower() or "lighting"
    area_text = _rewrite_application_text(application_text, category)

    spec_bits = [
        _spec_fragment(specs, "power", "wattage", "watts"),
        _spec_fragment(specs, "voltage", "input voltage"),
        _spec_fragment(specs, "cct", "color temp", prefix="CCT "),
        _spec_fragment(specs, "ip rating", "ip"),
        _spec_fragment(specs, "efficacy", "lm/w"),
    ]
    spec_bits = [bit for bit in spec_bits if bit][:3]
    feature_bits = _polish_features_for_layout(features, specs)[:2]

    sentence_one = f"{name} is a {category_value} fixture for {area_text}."
    if spec_bits:
        sentence_two = f"It supports {', '.join(spec_bits)} for project-ready performance."
    elif feature_bits:
        sentence_two = f"It focuses on {', '.join(feature_bits)} for dependable installation."
    else:
        sentence_two = "It is arranged for dependable output, durable construction, and clean project documentation."

    return _limit_words(f"{sentence_one} {sentence_two}", PAGE_COPY_LIMITS["description_words"])


def _build_copy_generation_context(session_data, form_data):
    vendor_data = session_data.get("vendor_data")
    tds_data = session_data.get("tds_data")
    header = form_data.get("header", {}) if isinstance(form_data, dict) else {}
    key_specs = form_data.get("key_specs", {}) if isinstance(form_data, dict) else {}
    applications = form_data.get("application_area", {}) if isinstance(form_data, dict) else {}
    features = form_data.get("features", []) if isinstance(form_data, dict) else []

    context = {
        "product_name": header.get("product_name") or getattr(tds_data, "product_name", ""),
        "product_title": header.get("product_title") or getattr(tds_data, "product_title", ""),
        "category": header.get("category") or getattr(tds_data, "product_category", ""),
        "category_path": header.get("category_path") or getattr(tds_data, "category_path", ""),
        "application_area": applications.get("text", "") if isinstance(applications, dict) else "",
        "existing_description": ((form_data.get("product_description", {}) or {}).get("text", "") if isinstance(form_data, dict) else "") or getattr(tds_data, "product_description", ""),
        "existing_features": features or getattr(tds_data, "features", []) or [],
        "key_specs": {
            "power": key_specs.get("power_selectable") or getattr(tds_data, "wattage", ""),
            "voltage": key_specs.get("voltage") or getattr(tds_data, "input_voltage", ""),
            "efficacy": key_specs.get("efficacy") or getattr(tds_data, "efficacy", ""),
            "cct": key_specs.get("cct_selectable") or getattr(tds_data, "cct", ""),
            "lumens": key_specs.get("lumen_output") or getattr(tds_data, "lumens", ""),
            "cri": key_specs.get("cri") or getattr(tds_data, "cri", ""),
            "ip_rating": key_specs.get("ip_rating") or getattr(tds_data, "ip_rating", ""),
            "ik_rating": key_specs.get("ik_rating") or getattr(tds_data, "ik_rating", ""),
        },
        "vendor_applications": getattr(vendor_data, "applications", []) or getattr(vendor_data, "application_areas", []) or [],
        "vendor_features": getattr(vendor_data, "features", []) or [],
    }
    return json.dumps(context, indent=2)


def _generate_ai_copy(session_data, form_data, field, word_limit=None, item_count=None):
    if not AI_CLIENT_AVAILABLE or not get_ai_client:
        raise RuntimeError("AI copy generation is not available in this environment.")

    provider = session_data.get("provider") or AI_PROVIDER
    api_key = session_data.get("api_key")
    client = get_ai_client(provider, api_key)
    context = _build_copy_generation_context(session_data, form_data)

    if field == "description":
        target_words = max(40, min(int(word_limit or 100), 220))
        prompt = f"""
You are writing original technical marketing copy for an IKIO technical data sheet.
Rewrite the content so it is materially different from vendor phrasing, technically accurate, and readable.
Do not copy or closely mirror source sentences.
Use only plain English.
Keep the description close to {target_words} words.
Return strict JSON:
{{
  "description": "..."
}}
"""
        result = client.analyze_text(context, prompt=prompt)
        description = _normalize_whitespace(result.get("description") or result.get("raw_content"))
        if not description:
            raise RuntimeError("AI copy generation returned an empty description.")
        return {"description": _limit_words(description, target_words)}

    if field == "features":
        target_count = max(3, min(int(item_count or 6), 12))
        prompt = f"""
You are writing original technical bullet points for an IKIO technical data sheet.
Generate {target_count} concise feature bullets based on the provided product context.
Each bullet must be distinct, technically grounded, and ideally 4 to 9 words.
Avoid copying vendor wording, slogans, and repeated phrases.
Return strict JSON:
{{
  "features": ["...", "..."]
}}
"""
        result = client.analyze_text(context, prompt=prompt)
        features = result.get("features")
        if not isinstance(features, list):
            raw = result.get("raw_content", "")
            features = [line.strip("-• \t") for line in str(raw).splitlines() if line.strip()]
        features = _dedupe_preserve_order(features)[:target_count]
        if not features:
            raise RuntimeError("AI copy generation returned no features.")
        return {"features": [_limit_words(item, 10) for item in features]}

    raise ValueError("Unsupported content field requested.")


def _normalize_label(value):
    return re.sub(r"[^a-z0-9]+", " ", _clean_value(value).lower()).strip()


def _get_spec_value(specs_dict, *keys):
    """Best-effort lookup across extracted specification dictionaries with ambiguity control."""
    best_value = ""
    best_score = -10**9

    for key_index, key in enumerate(keys):
        normalized_key = _normalize_label(key)
        if not normalized_key:
            continue

        for spec_key, spec_value in specs_dict.items():
            cleaned = _clean_value(spec_value)
            if not cleaned:
                continue

            normalized_spec_key = _normalize_label(spec_key)
            if not normalized_spec_key:
                continue

            score = None
            if normalized_spec_key == normalized_key:
                score = 1000 - key_index
            elif normalized_spec_key.startswith(f"{normalized_key} "):
                score = 850 - key_index
            else:
                spec_tokens = normalized_spec_key.split()
                key_tokens = normalized_key.split()
                if all(token in spec_tokens for token in key_tokens):
                    score = 650 - key_index - max(0, len(spec_tokens) - len(key_tokens)) * 15
                elif len(normalized_key) >= 6 and normalized_key in normalized_spec_key:
                    score = 300 - key_index

            if score is None:
                continue

            # Prevent common false positives like "Power" -> "Power Factor".
            if normalized_key == "power" and any(token in normalized_spec_key for token in ("factor", "supply", "driver")):
                score -= 500
            if normalized_key == "current" and "surge" in normalized_spec_key:
                score -= 200
            if normalized_key == "location" and "application" in normalized_spec_key:
                score -= 120

            if score > best_score:
                best_score = score
                best_value = cleaned

    return best_value


def _encode_image_bytes(image_bytes):
    if isinstance(image_bytes, (bytes, bytearray)):
        return base64.b64encode(bytes(image_bytes)).decode('utf-8')
    return None


def _pick_extracted_image(tds_data, *keywords):
    extracted_images = getattr(tds_data, 'extracted_images', []) or []
    lowered_keywords = [keyword.lower() for keyword in keywords]
    for image in extracted_images:
        image_type = _clean_value(image.get('image_type', '')).lower()
        if any(keyword in image_type for keyword in lowered_keywords):
            image_bytes = image.get('image_data')
            if isinstance(image_bytes, (bytes, bytearray)):
                return bytes(image_bytes)
    return None


def _build_initial_image_slots(tds_data):
    slots = {
        "product_image": None,
        "dimension_diagram": None,
        "photometric_diagram": None,
        "wiring_diagram": None,
        "surface_mounting": None,
        "accessory_image_1": None,
        "accessory_image_2": None,
        "accessory_image_3": None,
        "accessory_image_4": None,
        "cert_badge_1": None,
        "cert_badge_2": None,
        "cert_badge_3": None,
        "cert_badge_4": None,
    }

    product_bytes = None
    if getattr(tds_data, 'product_images', None):
        first_product = tds_data.product_images[0]
        if isinstance(first_product, (bytes, bytearray)):
            product_bytes = bytes(first_product)
    if not product_bytes:
        product_bytes = _pick_extracted_image(tds_data, 'product')
    slots["product_image"] = _encode_image_bytes(product_bytes)

    dimension_bytes = getattr(tds_data, 'dimension_diagram_data', None) or _pick_extracted_image(tds_data, 'dimension')
    slots["dimension_diagram"] = _encode_image_bytes(dimension_bytes)

    photometric_bytes = (
        getattr(tds_data, 'photometrics_diagram_data', None)
        or next(
            (
                item.get('image_data')
                for item in (getattr(tds_data, 'beam_angle_diagrams', []) or [])
                if isinstance(item, dict) and isinstance(item.get('image_data'), (bytes, bytearray))
            ),
            None
        )
        or _pick_extracted_image(tds_data, 'photometric', 'beam_pattern')
    )
    slots["photometric_diagram"] = _encode_image_bytes(photometric_bytes)

    wiring_bytes = next(
        (
            item.get('image_data')
            for item in (getattr(tds_data, 'wiring_diagrams', []) or [])
            if isinstance(item, dict) and isinstance(item.get('image_data'), (bytes, bytearray))
        ),
        None
    ) or _pick_extracted_image(tds_data, 'wiring')
    slots["wiring_diagram"] = _encode_image_bytes(wiring_bytes)

    mounting_bytes = next(
        (
            getattr(item, 'image_data', None)
            for item in (getattr(tds_data, 'mounting_options', []) or [])
            if getattr(item, 'image_data', None)
        ),
        None
    ) or _pick_extracted_image(tds_data, 'mounting')
    slots["surface_mounting"] = _encode_image_bytes(mounting_bytes)

    for index, accessory in enumerate((getattr(tds_data, 'accessories', []) or [])[:4], start=1):
        slots[f"accessory_image_{index}"] = _encode_image_bytes(getattr(accessory, 'image_data', None))

    for index, badge in enumerate((getattr(tds_data, 'certification_badges', []) or [])[:4], start=1):
        slots[f"cert_badge_{index}"] = _encode_image_bytes(badge)

    return slots


def _build_variant_pairs(vendor_data, all_specs):
    """Build the urgent-sheet style label/value rows from vendor data."""
    variants = getattr(vendor_data, 'variants', []) or []
    if variants:
        preferred_labels = [
            ("Power", ("power", "wattage")),
            ("Voltage", ("voltage", "input_voltage")),
            ("Power Factor", ("power_factor", "pf")),
            ("Total Harmonic Distortion (THD)", ("thd", "harmonic")),
            ("Lumen Output", ("lumens", "lumen_output")),
            ("Efficacy", ("efficacy",)),
            ("CCT", ("cct", "color_temp")),
            ("Beam Angle", ("beam_angle",)),
            ("Color Rendering Index (CRI)", ("cri",)),
            ("Dimmable Lighting Control", ("dimming", "dimmable")),
            ("Operating Temperature", ("operating_temperature", "ambient_temperature")),
            ("Suitable Location", ("suitable_location", "location")),
            ("Housing", ("housing", "body_material")),
            ("Diffuser", ("diffuser",)),
            ("Base Height (Inches)", ("base_height",)),
            ("Finish", ("finish", "color")),
            ("Mounting Options", ("mounting", "mounting_type")),
        ]
        rows = []
        for label, keys in preferred_labels:
            values = []
            for variant in variants:
                if not isinstance(variant, dict):
                    continue
                found = ""
                for key in keys:
                    found = _clean_value(variant.get(key))
                    if found:
                        break
                if found:
                    values.append(found)
            joined = " | ".join(dict.fromkeys(values))
            rows.append({"label": label, "value": joined})
        rows = [row for row in rows if row["label"] or row["value"]]
        if rows:
            return rows[:23]

    fallback_pairs = [
        ("Power", _get_spec_value(all_specs, 'power', 'wattage', 'watts')),
        ("Voltage", _get_spec_value(all_specs, 'voltage', 'input voltage')),
        ("Power Factor", _get_spec_value(all_specs, 'power factor', 'pf')),
        ("Total Harmonic Distortion (THD)", _get_spec_value(all_specs, 'thd', 'harmonic')),
        ("Lumen Output", _get_spec_value(all_specs, 'lumens', 'lumen', 'flux')),
        ("Efficacy", _get_spec_value(all_specs, 'efficacy', 'lm/w')),
        ("CCT", _get_spec_value(all_specs, 'color temp', 'cct', 'kelvin')),
        ("Beam Angle", _get_spec_value(all_specs, 'beam angle')),
        ("Color Rendering Index (CRI)", _get_spec_value(all_specs, 'cri', 'color rendering')),
        ("Dimmable Lighting Control", _get_spec_value(all_specs, 'dimm', 'control')),
        ("Operating Temperature", _get_spec_value(all_specs, 'operating temp', 'ambient')),
        ("Suitable Location", _get_spec_value(all_specs, 'location', 'suitable')),
        ("Housing", _get_spec_value(all_specs, 'housing', 'body')),
        ("Diffuser", _get_spec_value(all_specs, 'diffuser')),
        ("Base Height (Inches)", _get_spec_value(all_specs, 'base height')),
        ("Finish", _get_spec_value(all_specs, 'finish', 'color')),
        ("Mounting Options", _get_spec_value(all_specs, 'mounting', 'mount')),
    ]
    pairs = [{"label": label, "value": value} for label, value in fallback_pairs]
    return pairs[:23]


def _split_badge_terms(value):
    """Split free-form certification text into badge-friendly terms."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        terms = []
        for item in value:
            terms.extend(_split_badge_terms(item))
        return terms

    text = _clean_value(value)
    if not text:
        return []

    parts = re.split(r'[\n,;/|]+', text)
    return [part.strip(" -:.") for part in parts if part.strip(" -:.")]


def _dedupe_badge_terms(terms):
    ordered = []
    seen = set()
    for term in terms:
        cleaned = re.sub(r'\s+', ' ', _clean_value(term)).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ordered


def _looks_selectable(value):
    text = _clean_value(value).lower()
    if not text:
        return False
    return any(marker in text for marker in ("selectable", "/", "3cct", "4cct", "5cct", "multi", "tunable"))


def _build_auto_badge_terms(form_data, tds_data=None, vendor_data=None):
    if not isinstance(form_data, dict):
        form_data = {}

    product_profile = match_product_profile(vendor_data=vendor_data, tds_data=tds_data, form_data=form_data)
    profile_terms = get_profile_badge_terms(product_profile)

    header = form_data.get('header', {})
    key_specs = form_data.get('key_specs', {})
    product_specs = form_data.get('product_specs', {})
    qualifications = form_data.get('qualifications', {})
    features = form_data.get('features', []) or []

    terms = list(profile_terms)
    terms.extend(getattr(vendor_data, 'certifications', []) or [])
    terms.extend(getattr(tds_data, 'certifications', []) or [])

    if isinstance(qualifications, dict):
        terms.extend(_split_badge_terms(qualifications.get('text')))

    terms.extend(_split_badge_terms(features))

    ip_rating = product_specs.get('ip_rating') or key_specs.get('ip_rating') or getattr(tds_data, 'ip_rating', '')
    if _clean_value(ip_rating):
        terms.append(_clean_value(ip_rating))

    cct_value = key_specs.get('cct_selectable') or getattr(tds_data, 'cct', '')
    if _looks_selectable(cct_value):
        terms.append('CCT Selectable')

    power_value = key_specs.get('power_selectable') or getattr(tds_data, 'wattage', '')
    if _looks_selectable(power_value):
        terms.append('Power Selectable')

    dimming_value = product_specs.get('dimming_control') or getattr(tds_data, 'dimming', '')
    if _clean_value(dimming_value):
        terms.append('Dimmable')

    lowered_features = " ".join(str(item) for item in features).lower()
    if 'sensor' in lowered_features or 'motion' in lowered_features:
        terms.append('Sensor Ready')

    overview_text = header.get('product_overview') or getattr(tds_data, 'product_description', '')
    if 'energy star' in str(overview_text).lower():
        terms.append('Energy Star')

    return _dedupe_badge_terms(terms)


def _normalize_title_case(value):
    text = _clean_value(value)
    if not text:
        return ""
    words = []
    for word in text.split():
        if word.isupper() and len(word) <= 5:
            words.append(word)
        else:
            words.append(word[:1].upper() + word[1:] if word else word)
    return " ".join(words)


def _is_generic_product_label(value):
    text = _clean_value(value).lower()
    if not text:
        return True
    generic_phrases = (
        "luminaire",
        "lighting",
        "outdoor lights",
        "area luminaires",
        "vendor consolidation",
        "technical data sheet",
        "product specification",
    )
    return any(phrase in text for phrase in generic_phrases)


def _resolve_display_header(vendor_data, tds_data, product_profile=None):
    name = _clean_value(getattr(vendor_data, 'product_name', '') or getattr(tds_data, 'product_name', ''))
    series = _clean_value(getattr(vendor_data, 'product_series', '') or getattr(tds_data, 'product_series', ''))
    category = _clean_value(getattr(vendor_data, 'product_category', '') or getattr(tds_data, 'product_category', ''))
    tagline = _clean_value(getattr(vendor_data, 'tagline', ''))
    profile_header = get_profile_header(product_profile)

    display_name = name
    display_title = ""
    display_category = category

    if series and series.lower() not in name.lower():
        display_name = _normalize_title_case(series)
        display_title = _normalize_title_case(name)
    elif tagline and tagline.lower() not in name.lower():
        display_title = tagline
    elif category and category.lower() not in name.lower() and not _is_generic_product_label(category):
        display_title = _normalize_title_case(category)
        display_category = ""

    if not display_name or _is_generic_product_label(display_name):
        if series:
            display_name = _normalize_title_case(series)
        elif category and not _is_generic_product_label(category):
            display_name = _normalize_title_case(category)

    if not display_title and category and category.lower() != display_name.lower() and not _is_generic_product_label(category):
        display_title = _normalize_title_case(category)
        display_category = ""

    if display_category and display_title and display_category.lower() == display_title.lower():
        display_category = ""

    return {
        "product_name": profile_header.get("product_name") or display_name or "IKIO Product",
        "product_title": profile_header.get("product_title") or display_title,
        "category": profile_header.get("category") or display_category,
        "category_path": profile_header.get("category_path", ""),
    }


def _build_qualification_text(vendor_data, tds_data, all_specs, product_profile=None):
    derived_terms = list(get_profile_badge_terms(product_profile))
    derived_terms.extend(getattr(vendor_data, 'certifications', []) or [])
    derived_terms.extend(getattr(tds_data, 'certifications', []) or [])

    ip_rating = _get_spec_value(all_specs, 'ip rating', 'ip')
    if _clean_value(ip_rating):
        derived_terms.append(_clean_value(ip_rating))

    cct_value = _get_spec_value(all_specs, 'color temp', 'cct', 'kelvin')
    if _looks_selectable(cct_value):
        derived_terms.append('CCT Selectable')

    dimming_value = _get_spec_value(all_specs, 'dimm', 'dimming')
    if _clean_value(dimming_value):
        derived_terms.append('Dimmable')

    power_value = _get_spec_value(all_specs, 'power selectable', 'power', 'wattage')
    if _looks_selectable(power_value):
        derived_terms.append('Power Selectable')

    feature_text = " ".join(str(item) for item in getattr(tds_data, 'features', []) or [])
    if 'sensor' in feature_text.lower() or 'motion' in feature_text.lower():
        derived_terms.append('Sensor Ready')

    unique_terms = _dedupe_badge_terms(derived_terms)
    if unique_terms:
        return ", ".join(unique_terms[:8])

    source_count = len(getattr(vendor_data, 'source_file', '').split('|')) if getattr(vendor_data, 'source_file', '') else 1
    return f"Prepared from {source_count} vendor source document(s) and normalized into IKIO format."


def _refresh_certification_badges(tds_data, form_data):
    if not IMAGE_ASSET_MANAGER_AVAILABLE or not get_asset_manager:
        return

    terms = _build_auto_badge_terms(form_data, tds_data=tds_data)
    if not terms:
        return

    try:
        asset_manager = get_asset_manager()
        badges = asset_manager.get_certification_badges(terms)
        if badges:
            tds_data.certification_badges = [
                asset_manager.resize_image(badge, max_width=200, max_height=200)
                for badge in badges[:4]
                if badge
            ]
    except Exception as exc:
        print(f"[WARNING] Could not refresh certification badges: {exc}")


def _build_ordering_table(vendor_data):
    raw_ordering = _find_raw_ordering_table(vendor_data)
    if raw_ordering:
        return raw_ordering

    rows = []
    variants = getattr(vendor_data, 'variants', []) or []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        rows.append([
            _clean_value(variant.get('part_number') or variant.get('model') or variant.get('sku')),
            _clean_value(variant.get('brand') or 'IKIO'),
            _clean_value(variant.get('model') or variant.get('series') or variant.get('family')),
            _clean_value(variant.get('power') or variant.get('wattage')),
            _clean_value(variant.get('cct') or variant.get('color_temp')),
        ])

    if not rows:
        model_numbers = getattr(vendor_data, 'model_numbers', []) or []
        for model in model_numbers[:8]:
            rows.append([_clean_value(model), 'IKIO', _clean_value(vendor_data.product_name), "", ""])

    headers = ["Brand", "Family/Version", "Variant", "Power (W)", "CCT (K)", "Distribution"]
    grouped_rows = []
    for row in rows[:12]:
        part_number = row[0] if len(row) > 0 else ""
        brand = row[1] if len(row) > 1 else "IKIO"
        model = row[2] if len(row) > 2 else ""
        power = row[3] if len(row) > 3 else ""
        cct = row[4] if len(row) > 4 else ""
        grouped_rows.append([brand, model, part_number, power, cct, ""])

    return {
        "headers": headers,
        "subheaders": [],
        "groups": [
            {"label": "LUMINAIRE FAMILY", "span": 3},
            {"label": "ELECTRICAL / LIGHTING PERFORMANCE", "span": 2},
            {"label": "OPTICS", "span": 1},
        ],
        "rows": grouped_rows,
    }


PRODUCT_SPEC_TABLE_HEADERS = [
    "Part Number",
    "Power Selectable",
    "Voltage",
    "Lumen Output",
    "Efficacy",
    "CRI",
    "Current",
    "CCT Selectable",
    "THD",
    "Light Distribution",
]


def _normalize_table_headers(headers):
    return [_clean_value(header).replace("\n", " ").strip() for header in (headers or [])]


def _normalize_table_cell(cell):
    text = _clean_value(cell)
    if not text:
        return ""
    return "\n".join(re.sub(r"\s+", " ", line).strip() for line in text.splitlines()).strip()


def _normalize_table_rows(rows, width):
    normalized_rows = []
    for row in rows or []:
        values = [_normalize_table_cell(cell) for cell in (row or [])]
        if width:
            values = (values + [""] * width)[:width]
        if any(values):
            normalized_rows.append(values)
    return normalized_rows


def _raw_table_payload(table):
    headers = _normalize_table_headers(getattr(table, 'headers', []) or [])
    subheaders = _normalize_table_headers(getattr(table, 'subheaders', []) or [])
    groups = getattr(table, 'groups', []) or []
    rows = getattr(table, 'rows', []) or []
    if not headers and rows:
        first_row = rows[0] if rows else []
        headers = _normalize_table_headers(first_row)
        rows = rows[1:] if any(_clean_value(cell) for cell in first_row) else rows
    width = len(headers) if headers else max((len(row or []) for row in rows), default=0)
    if width == 0:
        return None
    normalized_rows = _normalize_table_rows(rows, width)
    if not normalized_rows:
        return None
    return {
        "headers": headers or [f"Column {index + 1}" for index in range(width)],
        "subheaders": (subheaders + [""] * width)[:width] if subheaders else [],
        "groups": groups,
        "rows": normalized_rows,
    }


def _find_raw_product_spec_table(vendor_data):
    expected_headers = {_normalize_label(header) for header in PRODUCT_SPEC_TABLE_HEADERS}
    best_match = None
    best_score = 0

    for table in getattr(vendor_data, 'raw_tables', []) or []:
        payload = _raw_table_payload(table)
        if not payload:
            continue

        normalized_headers = {_normalize_label(header) for header in payload["headers"]}
        title = _normalize_label(getattr(table, 'title', ''))
        table_type = _normalize_label(getattr(table, 'table_type', ''))

        score = len(expected_headers.intersection(normalized_headers)) * 10
        if "spec" in title or "performance" in title:
            score += 12
        if "spec" in table_type:
            score += 12
        if _normalize_label("part number") in normalized_headers:
            score += 8
        if _normalize_label("lumen output") in normalized_headers:
            score += 8

        if score > best_score and len(payload["rows"]) >= 1:
            best_match = payload
            best_score = score

    return best_match if best_score >= 28 else None


def _find_raw_ordering_table(vendor_data):
    best_match = None
    best_score = 0
    ordering_keywords = {
        "ordering",
        "order",
        "luminaire family",
        "electrical",
        "construction",
        "mounting",
        "manufacturer",
        "finish",
    }

    for table in getattr(vendor_data, 'raw_tables', []) or []:
        payload = _raw_table_payload(table)
        if not payload:
            continue

        title = _normalize_label(getattr(table, 'title', ''))
        table_type = _normalize_label(getattr(table, 'table_type', ''))
        header_blob = " ".join(_normalize_label(header) for header in payload["headers"])

        score = 0
        if "order" in title or "ordering" in title:
            score += 20
        if "order" in table_type or "ordering" in table_type:
            score += 20
        if len(payload["headers"]) >= 8:
            score += 16
        for keyword in ordering_keywords:
            if keyword in header_blob or keyword in title:
                score += 6

        if score > best_score and len(payload["rows"]) >= 1:
            best_match = payload
            best_score = score

    return best_match if best_score >= 24 else None


def _build_product_spec_table(vendor_data, all_specs):
    raw_table = _find_raw_product_spec_table(vendor_data)
    if raw_table:
        return {
            "headers": raw_table["headers"],
            "rows": raw_table["rows"],
        }
    return {
        "headers": PRODUCT_SPEC_TABLE_HEADERS,
        "rows": _build_product_specification_rows(vendor_data, all_specs),
    }


def _split_product_spec_tokens(value):
    text = _clean_value(value)
    if not text:
        return []

    protected = (
        text.replace("lm/W", "lm__per__W")
        .replace("lm/w", "lm__per__w")
        .replace("LM/W", "LM__per__W")
    )

    parts = []
    current = []
    depth = 0
    for char in protected:
        if char == '(':
            depth += 1
        elif char == ')' and depth > 0:
            depth -= 1

        if char == '/' and depth == 0:
            token = "".join(current).strip()
            if token:
                parts.append(token)
            current = []
            continue
        current.append(char)

    tail = "".join(current).strip()
    if tail:
        parts.append(tail)

    return [
        part.replace("lm__per__W", "lm/W").replace("lm__per__w", "lm/w").strip()
        for part in parts
        if part.strip()
    ]


def _strip_parenthetical_suffix(value):
    text = _clean_value(value)
    return re.sub(r"\s*\(([^()]*)\)\s*$", "", text).strip()


def _extract_parenthetical_suffix(value):
    text = _clean_value(value)
    match = re.search(r"\(([^()]*)\)\s*$", text)
    return match.group(1).strip() if match else ""


def _expand_product_spec_rows(base_row):
    power_tokens = _split_product_spec_tokens(base_row["power"])
    lumen_tokens = _split_product_spec_tokens(base_row["lumens"])
    efficacy_tokens = _split_product_spec_tokens(base_row["efficacy"])
    current_tokens = _split_product_spec_tokens(base_row["current"])
    distribution_tokens = _split_product_spec_tokens(base_row["light_distribution"])

    if not distribution_tokens:
        derived_distribution = [
            _extract_parenthetical_suffix(token)
            for token in lumen_tokens or efficacy_tokens
        ]
        distribution_tokens = [token for token in derived_distribution if token]

    if distribution_tokens and lumen_tokens:
        lumen_tokens = [_strip_parenthetical_suffix(token) for token in lumen_tokens]
    if distribution_tokens and efficacy_tokens:
        efficacy_tokens = [_strip_parenthetical_suffix(token) for token in efficacy_tokens]

    subrow_count = max(
        len(power_tokens),
        len(lumen_tokens),
        len(efficacy_tokens),
        len(current_tokens),
        len(distribution_tokens),
        1,
    )

    def token_at(tokens, index, repeat_single=True):
        if not tokens:
            return ""
        if len(tokens) == subrow_count:
            return tokens[index]
        if len(tokens) == 1 and repeat_single:
            return tokens[0]
        if index < len(tokens):
            return tokens[index]
        return tokens[-1] if repeat_single else ""

    rows = []
    for index in range(subrow_count):
        rows.append([
            base_row["part_number"],
            token_at(power_tokens, index),
            base_row["voltage"],
            token_at(lumen_tokens, index),
            token_at(efficacy_tokens, index),
            base_row["cri"],
            token_at(current_tokens, index),
            base_row["cct"],
            base_row["thd"],
            token_at(distribution_tokens, index),
        ])

    return rows


def _build_product_specification_rows(vendor_data, all_specs):
    rows = []
    variants = getattr(vendor_data, 'variants', []) or []
    fallback_part_number = (
        _clean_value(getattr(vendor_data, 'part_number_structure', ''))
        or _clean_value(getattr(vendor_data, 'ordering_info', {}).get('example') if isinstance(getattr(vendor_data, 'ordering_info', {}), dict) else "")
        or _clean_value((getattr(vendor_data, 'model_numbers', []) or [""])[0])
    )

    def build_row_dict(part_number="", variant=None):
        variant = variant or {}
        return {
            "part_number": _clean_value(part_number or variant.get('part_number') or variant.get('model') or fallback_part_number),
            "power": _clean_value(variant.get('power') or variant.get('wattage') or _get_spec_value(all_specs, 'power', 'wattage', 'watts')),
            "voltage": _clean_value(variant.get('voltage') or _get_spec_value(all_specs, 'voltage', 'input voltage')),
            "lumens": _clean_value(variant.get('lumens') or variant.get('lumen_output') or _get_spec_value(all_specs, 'lumens', 'lumen', 'flux')),
            "efficacy": _clean_value(variant.get('efficacy') or _get_spec_value(all_specs, 'efficacy', 'efficiency', 'lm/w')),
            "cri": _clean_value(variant.get('cri') or _get_spec_value(all_specs, 'cri', 'color rendering', 'ra')),
            "current": _clean_value(variant.get('current') or variant.get('input_current') or _get_spec_value(all_specs, 'current', 'input current')),
            "cct": _clean_value(variant.get('cct') or variant.get('color_temp') or _get_spec_value(all_specs, 'color temp', 'cct', 'kelvin')),
            "thd": _clean_value(variant.get('thd') or _get_spec_value(all_specs, 'thd', 'harmonic')),
            "light_distribution": _clean_value(
                variant.get('light_distribution')
                or variant.get('distribution')
                or variant.get('beam_angle')
                or _get_spec_value(all_specs, 'light distribution', 'distribution', 'beam angle', 'beam')
            ),
        }

    if variants:
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            row = build_row_dict(variant=variant)
            if any(row.values()):
                rows.extend(_expand_product_spec_rows(row))

    if not rows:
        model_numbers = getattr(vendor_data, 'model_numbers', []) or []
        for model in model_numbers:
            row = build_row_dict(part_number=model)
            if any(row.values()):
                rows.extend(_expand_product_spec_rows(row))

    if not rows:
        row = build_row_dict()
        if any(value for key, value in row.items() if key != "part_number"):
            rows.extend(_expand_product_spec_rows(row))

    return rows[:18]


def _unique_list(items):
    seen = []
    for item in items:
        cleaned = _clean_value(item)
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _merge_spec_dicts(*dicts):
    merged = {}
    for current in dicts:
        for key, value in (current or {}).items():
            cleaned = _clean_value(value)
            if cleaned:
                merged[key] = cleaned
    return merged


def _combine_vendor_specs(vendor_items):
    """Merge multiple extracted vendor documents into one consolidated dataset."""
    if not vendor_items:
        return VendorSpecData()
    if len(vendor_items) == 1:
        return vendor_items[0]

    primary = vendor_items[0]
    combined = VendorSpecData(
        product_name=_clean_value(primary.product_name),
        product_series=" / ".join(_unique_list([item.product_series for item in vendor_items])),
        product_category=_clean_value(primary.product_category),
        product_description="\n\n".join(_unique_list([item.product_description for item in vendor_items])),
        tagline=_clean_value(primary.tagline),
        model_numbers=_unique_list([model for item in vendor_items for model in (item.model_numbers or [])]),
        features=_unique_list([feature for item in vendor_items for feature in (item.features or [])]),
        applications=_unique_list([app for item in vendor_items for app in (item.applications or [])]),
        electrical_specs=_merge_spec_dicts(*[item.electrical_specs for item in vendor_items]),
        optical_specs=_merge_spec_dicts(*[item.optical_specs for item in vendor_items]),
        physical_specs=_merge_spec_dicts(*[item.physical_specs for item in vendor_items]),
        environmental_specs=_merge_spec_dicts(*[item.environmental_specs for item in vendor_items]),
        lifespan_specs=_merge_spec_dicts(*[item.lifespan_specs for item in vendor_items]),
        component_specs=_merge_spec_dicts(*[item.component_specs for item in vendor_items]),
        packaging_info=_merge_spec_dicts(*[item.packaging_info for item in vendor_items]),
        ordering_info=_merge_spec_dicts(*[item.ordering_info for item in vendor_items]),
        part_number_structure=" | ".join(_unique_list([item.part_number_structure for item in vendor_items])),
        certifications=_unique_list([cert for item in vendor_items for cert in (item.certifications or [])]),
        accessories_included=[acc for item in vendor_items for acc in (item.accessories_included or [])],
        accessories_sold_separately=[acc for item in vendor_items for acc in (item.accessories_sold_separately or [])],
        mounting_options=[opt for item in vendor_items for opt in (item.mounting_options or [])],
        images=[img for item in vendor_items for img in (item.images or [])],
        dimension_diagram=primary.dimension_diagram,
        beam_angle_diagrams=[img for item in vendor_items for img in (item.beam_angle_diagrams or [])],
        wiring_diagrams=[img for item in vendor_items for img in (item.wiring_diagrams or [])],
        raw_tables=[table for item in vendor_items for table in (item.raw_tables or [])],
        source_file=" | ".join([Path(item.source_file).name for item in vendor_items if item.source_file]),
        page_count=sum(item.page_count or 0 for item in vendor_items),
        extraction_confidence=sum(item.extraction_confidence or 0 for item in vendor_items) / len(vendor_items),
    )

    if not combined.product_name:
        combined.product_name = "Consolidated Technical Sheet"
    if not combined.product_category:
        combined.product_category = "LIGHTING | CONSOLIDATED"
    if not combined.dimension_diagram:
        combined.dimension_diagram = next((item.dimension_diagram for item in vendor_items if item.dimension_diagram), None)

    return combined


def _polish_header_value(value, fallback):
    cleaned = _clean_value(value)
    return cleaned or fallback


def _generate_fallback_description(product_name, category, features, specs):
    return _polish_description_for_layout(product_name, category, features, specs, "")


def _generate_fallback_features(product_name, specs):
    suggestions = [
        f"Application-ready {product_name} platform",
        _get_spec_value(specs, 'efficacy', 'lm/w') and f"High-efficiency output up to {_get_spec_value(specs, 'efficacy', 'lm/w')}",
        _get_spec_value(specs, 'cct', 'color temp') and f"Configurable color temperature {_get_spec_value(specs, 'cct', 'color temp')}",
        _get_spec_value(specs, 'voltage') and f"Wide input voltage compatibility {_get_spec_value(specs, 'voltage')}",
        _get_spec_value(specs, 'ip rating', 'ip') and f"Protected construction rated {_get_spec_value(specs, 'ip rating', 'ip')}",
        "Professional-grade material and finish detailing",
        "Balanced optical and thermal design for long service life",
        "Specification-driven configuration for project submittals",
    ]
    return _polish_features_for_layout([item for item in suggestions if item][:8], specs)


def _import_fitz():
    try:
        import fitz  # type: ignore
        return fitz
    except Exception:
        import pymupdf as fitz  # type: ignore
        return fitz


def _render_pdf_preview(result_path):
    preview_image = None
    try:
        fitz = _import_fitz()
        doc = fitz.open(result_path)
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        img_bytes = pix.tobytes("png")
        preview_image = base64.b64encode(img_bytes).decode('utf-8')
        doc.close()
    except Exception as e:
        print(f"Preview generation failed: {e}")
    return preview_image


def _render_pdf_pages(result_path):
    pages = []
    try:
        fitz = _import_fitz()
        doc = fitz.open(result_path)
        for index, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
            img_bytes = pix.tobytes("png")
            pages.append({
                "page": index + 1,
                "image": base64.b64encode(img_bytes).decode('utf-8'),
                "width": page.rect.width,
                "height": page.rect.height,
            })
        doc.close()
    except Exception as e:
        print(f"Preview page generation failed: {e}")
    return pages


def _render_vendor_pages(pdf_paths, max_pages_per_doc=6, max_total_pages=12, scale=1.1):
    pages = []
    try:
        fitz = _import_fitz()
        total_pages = 0
        for source_index, pdf_path in enumerate(pdf_paths, start=1):
            doc = fitz.open(str(pdf_path))
            source_name = Path(pdf_path).name
            try:
                page_limit = min(len(doc), max_pages_per_doc, max(0, max_total_pages - total_pages))
                for page_index in range(page_limit):
                    page = doc[page_index]
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    pages.append({
                        "id": f"vendor_{source_index}_{page_index + 1}",
                        "source_name": source_name,
                        "page": page_index + 1,
                        "image": base64.b64encode(pix.tobytes("png")).decode('utf-8'),
                        "width": pix.width,
                        "height": pix.height,
                    })
                    total_pages += 1
                    if total_pages >= max_total_pages:
                        return pages
            finally:
                doc.close()
    except Exception as e:
        print(f"Vendor page rendering failed: {e}")
    return pages


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "enhanced_available": ENHANCED_AVAILABLE
    })


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get application configuration"""
    return jsonify({
        "providers": {
            "groq": {
                "name": "Groq (Fast, FREE)",
                "configured": bool(GROQ_API_KEY),
                "free": True,
                "vision": False
            },
            "gemini": {
                "name": "Google Gemini (Vision, FREE)",
                "configured": bool(GEMINI_API_KEY),
                "free": True,
                "vision": True
            },
            "ollama": {
                "name": "Ollama (Local, FREE)",
                "configured": True,
                "free": True,
                "vision": True
            },
            "openai": {
                "name": "OpenAI (Paid)",
                "configured": bool(OPENAI_API_KEY),
                "free": False,
                "vision": True
            }
        },
        "default_provider": AI_PROVIDER,
        "enhanced_available": ENHANCED_AVAILABLE
    })


@app.route('/api/extract', methods=['POST'])
def extract_from_pdf():
    """
    Extract data from uploaded PDF for form auto-fill
    Returns structured form data that can be edited
    """
    try:
        files = request.files.getlist('files')
        if not files and 'file' in request.files:
            files = [request.files['file']]
        if not files:
            return jsonify({"error": "No file uploaded"}), 400

        valid_files = []
        for file in files:
            if not file or file.filename == '':
                continue
            if not file.filename.lower().endswith('.pdf'):
                return jsonify({"error": "Only PDF files are supported"}), 400
            valid_files.append(file)

        if not valid_files:
            return jsonify({"error": "No valid PDF files selected"}), 400
        
        # Get parameters
        provider = request.form.get('provider', AI_PROVIDER)
        api_key = request.form.get('api_key', '')
        processing_mode = request.form.get('processing_mode', 'standard')
        
        # Use configured key if not provided
        if not api_key:
            if provider == 'groq':
                api_key = GROQ_API_KEY
            elif provider == 'gemini':
                api_key = GEMINI_API_KEY
            elif provider == 'openai':
                api_key = OPENAI_API_KEY
            elif provider == 'ollama':
                api_key = None

        tmp_paths = []
        vendor_docs = []
        for uploaded_file in valid_files:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                uploaded_file.save(tmp_file.name)
                tmp_paths.append(tmp_file.name)

            tmp_path = tmp_paths[-1]
            if processing_mode == 'enhanced' and ENHANCED_AVAILABLE and process_enhanced:
                vendor_doc = process_enhanced(tmp_path, provider=provider, api_key=api_key)
            else:
                vendor_doc = process_vendor_spec(tmp_path, api_key=api_key, provider=provider)

            if AI_ENHANCER_AVAILABLE and enhance_vendor_data:
                try:
                    vendor_doc = enhance_vendor_data(
                        vendor_doc,
                        provider=provider,
                        api_key=api_key
                    )
                except Exception as _enhance_err:
                    print(f"[WARNING] AI enhancement skipped: {_enhance_err}")

            vendor_docs.append(vendor_doc)

        if vendor_docs:
            vendor_data = _combine_vendor_specs(vendor_docs)
            tds_data = map_vendor_to_tds(vendor_data)

            session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + os.urandom(4).hex()

            images = []
            for i, img in enumerate(tds_data.extracted_images):
                if img.get('image_data'):
                    img_b64 = base64.b64encode(img['image_data']).decode('utf-8')
                    images.append({
                        'id': f'img_{i}',
                        'data': img_b64,
                        'type': img.get('image_type', 'product'),
                        'width': img.get('width', 0),
                        'height': img.get('height', 0),
                        'page': img.get('page_number', 1),
                        'description': img.get('description', '')
                    })

            dimension_image = None
            if tds_data.dimension_diagram_data:
                dimension_image = base64.b64encode(tds_data.dimension_diagram_data).decode('utf-8')

            form_data = build_form_data(tds_data, vendor_data)
            vendor_pages = _render_vendor_pages(tmp_paths)
            standard_badges = []
            if IMAGE_ASSET_MANAGER_AVAILABLE and get_asset_manager:
                try:
                    asset_manager = get_asset_manager()
                    badge_terms = _build_auto_badge_terms(form_data, tds_data=tds_data, vendor_data=vendor_data)
                    if badge_terms:
                        badge_bytes_list = asset_manager.get_certification_badges(badge_terms)
                        standard_badges = [
                            base64.b64encode(badge).decode('utf-8')
                            for badge in badge_bytes_list
                        ]
                except Exception as e:
                    print(f"[WARNING] Could not load standard badges: {e}")

            extracted_sessions[session_id] = {
                'tds_data': tds_data,
                'vendor_data': vendor_data,
                'provider': provider,
                'api_key': api_key,
                'vendor_documents': [Path(item.source_file).name for item in vendor_docs if item.source_file],
                'vendor_pages': vendor_pages,
                'created': datetime.now().isoformat()
            }

            for tmp_path in tmp_paths:
                try:
                    os.unlink(tmp_path)
                except:
                    pass

            return jsonify({
                "success": True,
                "session_id": session_id,
                "form_data": form_data,
                "images": images,
                "dimension_image": dimension_image,
                "vendor_pages": vendor_pages,
                "standard_badges": standard_badges,
                "extraction_confidence": vendor_data.extraction_confidence if hasattr(vendor_data, 'extraction_confidence') else 0.8
            })
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            file.save(tmp_file.name)
            tmp_path = tmp_file.name
        
        try:
            # Process the PDF
            if processing_mode == 'enhanced' and ENHANCED_AVAILABLE and process_enhanced:
                vendor_data = process_enhanced(tmp_path, provider=provider, api_key=api_key)
            else:
                vendor_data = process_vendor_spec(tmp_path, api_key=api_key, provider=provider)
            
            # ── AI Enhancement Step ──────────────────────────────────────
            # Intelligently rewrite and fill in content using AI before mapping
            if AI_ENHANCER_AVAILABLE and enhance_vendor_data:
                try:
                    vendor_data = enhance_vendor_data(
                        vendor_data,
                        provider=provider,
                        api_key=api_key
                    )
                except Exception as _enhance_err:
                    print(f"[WARNING] AI enhancement skipped: {_enhance_err}")
            # ────────────────────────────────────────────────────────────────

            # Map to IKIO format
            tds_data = map_vendor_to_tds(vendor_data)
            
            # Generate session ID
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + os.urandom(4).hex()
            
            # Convert images to base64 for frontend
            images = []
            for i, img in enumerate(tds_data.extracted_images):
                if img.get('image_data'):
                    img_b64 = base64.b64encode(img['image_data']).decode('utf-8')
                    images.append({
                        'id': f'img_{i}',
                        'data': img_b64,
                        'type': img.get('image_type', 'product'),
                        'width': img.get('width', 0),
                        'height': img.get('height', 0),
                        'page': img.get('page_number', 1),
                        'description': img.get('description', '')
                    })
            
            # Dimension diagram
            dimension_image = None
            if tds_data.dimension_diagram_data:
                dimension_image = base64.b64encode(tds_data.dimension_diagram_data).decode('utf-8')
            
            # Build structured form data matching PHP form structure
            form_data = build_form_data(tds_data, vendor_data)
            vendor_pages = _render_vendor_pages([tmp_path])

            # Include standard certification badges in response
            standard_badges = []
            if IMAGE_ASSET_MANAGER_AVAILABLE and get_asset_manager:
                try:
                    asset_manager = get_asset_manager()
                    badge_terms = _build_auto_badge_terms(form_data, tds_data=tds_data, vendor_data=vendor_data)
                    if badge_terms:
                        badge_bytes_list = asset_manager.get_certification_badges(badge_terms)
                        standard_badges = [
                            base64.b64encode(badge).decode('utf-8')
                            for badge in badge_bytes_list
                        ]
                except Exception as e:
                    print(f"[WARNING] Could not load standard badges: {e}")
            
            # Store for later generation
            extracted_sessions[session_id] = {
                'tds_data': tds_data,
                'vendor_data': vendor_data,
                'vendor_pages': vendor_pages,
                'created': datetime.now().isoformat()
            }
            
            return jsonify({
                "success": True,
                "session_id": session_id,
                "form_data": form_data,
                "images": images,
                "dimension_image": dimension_image,
                "vendor_pages": vendor_pages,
                "standard_badges": standard_badges,  # Standard certification/warranty badges
                "extraction_confidence": vendor_data.extraction_confidence if hasattr(vendor_data, 'extraction_confidence') else 0.8
            })
        
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def build_form_data(tds_data, vendor_data):
    """Build structured form data matching the expanded TDS form structure"""

    # Combine all specs
    all_specs = {
        **getattr(vendor_data, 'electrical_specs', {}),
        **getattr(vendor_data, 'optical_specs', {}),
        **getattr(vendor_data, 'physical_specs', {}),
        **getattr(vendor_data, 'environmental_specs', {}),
        **getattr(vendor_data, 'lifespan_specs', {}),
        **getattr(vendor_data, 'component_specs', {})
    }
    
    performance_table_payload = _build_product_spec_table(vendor_data, all_specs)
    performance_headers = performance_table_payload["headers"]
    performance_rows = performance_table_payload["rows"]

    variant_pairs = _build_variant_pairs(vendor_data, all_specs)
    ordering_information = _build_ordering_table(vendor_data)
    application_text = getattr(vendor_data, 'application_areas', None) or getattr(vendor_data, 'applications', None) or []
    if isinstance(application_text, list):
        application_text = ", ".join([_clean_value(item) for item in application_text if _clean_value(item)])
    application_text = _clean_value(application_text)
    product_profile = match_product_profile(vendor_data=vendor_data, tds_data=tds_data)
    profile_warranty = get_profile_warranty(product_profile)
    display_header = _resolve_display_header(vendor_data, tds_data, product_profile=product_profile)
    polished_name = _polish_header_value(display_header["product_name"], "Consolidated IKIO Spec Sheet")
    polished_category = _polish_header_value(display_header["category"] or tds_data.product_category or getattr(vendor_data, 'product_category', ''), "Lighting Solutions")
    polished_features = _polish_features_for_layout(
        tds_data.features or getattr(vendor_data, 'features', []) or _generate_fallback_features(polished_name, all_specs),
        all_specs,
    )
    polished_description = _polish_description_for_layout(
        polished_name,
        polished_category,
        tds_data.features or getattr(vendor_data, 'features', []),
        all_specs,
        application_text,
    )
    application_text = _rewrite_application_text(application_text, polished_category)
    warranty_years = profile_warranty.get("years") or _get_spec_value(all_specs, 'warranty') or "5 years"
    warranty_text = (
        profile_warranty.get("text", "")
        or all_specs.get("Warranty Text", "")
        or getattr(vendor_data, 'warranty_limitation', '')
        or f"{warranty_years} limited warranty covering defects in materials and workmanship under normal use and proper installation."
    )
    if not application_text:
        application_text = "Commercial interiors, retrofit projects, architectural spaces, and specification-driven lighting installations"
    initial_images = _build_initial_image_slots(tds_data)

    form_data = {
        "header": {
            "item_sku": "",
            "project_name": "IKIO",
            "catalog_number": getattr(vendor_data, 'part_number_structure', '') or (vendor_data.model_numbers[0] if getattr(vendor_data, 'model_numbers', None) else ""),
            "fixture_schedule": "",
            "issue_date": datetime.now().strftime("%Y-%m-%d"),
            "category_path": display_header.get("category_path") or getattr(vendor_data, 'product_category', '') or tds_data.product_category or "OUTDOOR LIGHTS | FLOOD LIGHTS",
            "category": display_header["category"] or getattr(vendor_data, 'product_category', '') or tds_data.product_category or "Lighting",
            "subcategory": getattr(vendor_data, 'product_series', '') or "Vendor Consolidation",
            "product_name": display_header["product_name"],
            "product_title": display_header["product_title"],
            "product_overview": polished_description,
            "tagline": display_header["category"] or getattr(vendor_data, 'tagline', '') or f"Polished performance for {polished_category.lower()}",
        },

        "key_specs": {
            "power_selectable": _get_spec_value(all_specs, 'power', 'wattage', 'watts'),
            "voltage": _get_spec_value(all_specs, 'voltage', 'input voltage'),
            "current": _get_spec_value(all_specs, 'current', 'input current'),
            "efficacy": _get_spec_value(all_specs, 'efficacy', 'efficiency', 'lm/w'),
            "cct_selectable": _get_spec_value(all_specs, 'color temp', 'cct', 'kelvin'),
            "lumen_output": _get_spec_value(all_specs, 'lumens', 'lumen', 'flux'),
            "cri": _get_spec_value(all_specs, 'cri', 'color rendering', 'ra'),
            "light_distribution": _get_spec_value(all_specs, 'light distribution', 'distribution'),
            "ip_rating": _get_spec_value(all_specs, 'ip rating', 'ip'),
            "ik_rating": _get_spec_value(all_specs, 'ik rating', 'ik', 'impact'),
        },

        "features": polished_features,

        "qualifications": {
            "text": _build_qualification_text(vendor_data, tds_data, all_specs, product_profile=product_profile),
        },

        "warranty": {
            "years": warranty_years,
            # Use AI-enhanced warranty text if available, otherwise default
            "limitation": warranty_text,
        },

        "product_specs": {
            "power_factor": _get_spec_value(all_specs, 'power factor', 'pf'),
            "thd": _get_spec_value(all_specs, 'thd', 'harmonic'),
            "beam_angle": _get_spec_value(all_specs, 'beam angle', 'beam'),
            "dimming_control": _get_spec_value(all_specs, 'dimm', 'dimming'),
            "operating_temperature": _get_spec_value(all_specs, 'operating temp', 'ambient'),
            "suitable_location": _get_spec_value(all_specs, 'location', 'suitable'),
            "ip_rating": _get_spec_value(all_specs, 'ip rating', 'ip'),
            "ik_rating": _get_spec_value(all_specs, 'ik rating', 'ik', 'impact'),
            "average_life": _get_spec_value(all_specs, 'life', 'l70', 'hours'),
            "warranty_years": warranty_years,
            "led_light_source": _get_spec_value(all_specs, 'led', 'source', 'chip'),
            "housing": _get_spec_value(all_specs, 'housing', 'body'),
            "cover_material_lens": _get_spec_value(all_specs, 'cover', 'lens', 'diffuser'),
            "diffuser": _get_spec_value(all_specs, 'diffuser'),
            "base_power_supply": _get_spec_value(all_specs, 'base', 'power supply', 'driver'),
            "finish": _get_spec_value(all_specs, 'finish', 'color'),
        },

        "performance_table": {
            "headers": performance_headers,
            "rows": performance_rows,
        },

        "variant_details": variant_pairs + [{"label": "", "value": ""} for _ in range(max(0, 23 - len(variant_pairs)))],

        "photometrics": {
            "ies_note": getattr(vendor_data, 'ies_file', '') or "",
        },

        "dimensions": {
            "product_length": tds_data.product_length or _get_spec_value(all_specs, 'length', 'product length', 'l'),
            "product_width": tds_data.product_width or _get_spec_value(all_specs, 'width', 'product width', 'w'),
            "product_height": tds_data.product_height or _get_spec_value(all_specs, 'height', 'product height', 'h'),
            "wire_length": tds_data.wire_length or _get_spec_value(all_specs, 'wire', 'wire length', 'cable length'),
            "net_weight": tds_data.net_weight or tds_data.product_weight or _get_spec_value(all_specs, 'weight', 'net weight'),
            "slip_fitter_length": tds_data.slip_fitter_length or "",
            "slip_fitter_width": tds_data.slip_fitter_width or "",
            "slip_fitter_height": tds_data.slip_fitter_height or "",
            "slip_fitter_weight": tds_data.slip_fitter_weight or "",
        },

        "epa_table": {
            "headers": [
                "Mounting Application", "Fixture Position 1", "2 @ 90 deg", "2 @ 180 deg",
                "3 @ 90 deg", "3 @ 120 deg", "4 @ 90 deg"
            ],
            "rows": [
                ["Horizontal (S)", "", "", "", "", "", ""],
                ["Horizontal (M)", "", "", "", "", "", ""],
                ["Horizontal (L)", "", "", "", "", "", ""],
                ["45 deg (S)", "", "", "", "", "", ""],
                ["45 deg (M)", "", "", "", "", "", ""],
                ["45 deg (L)", "", "", "", "", "", ""],
                ["Vertical (S)", "", "", "", "", "", ""],
                ["Vertical (M)", "", "", "", "", "", ""],
                ["Vertical (L)", "", "", "", "", "", ""],
            ],
        },

        "accessories": [
            {
                "name": acc.get('name', '') if isinstance(acc, dict) else getattr(acc, 'name', ''),
                "sku": acc.get('sku', '') if isinstance(acc, dict) else getattr(acc, 'part_number', ''),
                "code": acc.get('code', '') if isinstance(acc, dict) else '',
                "description": acc.get('description', '') if isinstance(acc, dict) else getattr(acc, 'description', ''),
                "download": acc.get('download', '') if isinstance(acc, dict) else '',
                "image": None,
            }
            for acc in (getattr(vendor_data, 'accessories_sold_separately', []) or [])
        ],

        "application_area": {
            "text": application_text,
        },

        "product_description": {
            "text": polished_description,
        },

        "ordering_information": ordering_information,

        "packaging_information": {
            "text": _clean_value(getattr(vendor_data, 'packaging_information', '')) or "Packaging details consolidated from the uploaded vendor source documents.",
        },

        "installation_instructions": {
            "text": _clean_value(getattr(vendor_data, 'installation_instructions', '')) or "Install in accordance with project requirements, local electrical code, and the final approved wiring configuration.",
        },

        "documents": {
            "note": "All supporting references were transformed from uploaded vendor documentation into an IKIO-ready urgent sheet.",
            "ies_file": _clean_value(getattr(vendor_data, 'ies_file', '')) or "Available on request",
            "lm79_report": _clean_value(getattr(vendor_data, 'lm79_report', '')) or "Available on request",
            "lm80_report": _clean_value(getattr(vendor_data, 'lm80_report', '')) or "Available on request",
        },

        "section_headings": {
            "overview": "OVERVIEW",
            "product_description": "Product Description",
            "features": "Features",
            "application_area": "Application Area",
            "warranty": "Warranty",
            "product_specifications": "Product Specifications",
            "download": "Download",
            "product_ordering_information": "Product Ordering Information",
            "performance_data": "Product Specifications",
            "packaging_information": "Packaging Information",
            "accessories_ordering_information": "Accessories Ordering Information",
            "wiring_diagram": "Wiring Diagram",
            "distributions": "Distributions",
            "installation_instructions": "Installation Instructions",
            "surface_mounting": "Surface Mounting",
        },

        "visual_layout": {
            "page_size": {"width": 612, "height": 792},
            "blocks": {
                "product_image": {"x": 44.0, "y": 138.0, "width": 238.0, "height": 316.0},
                "product_name": {"x": 20.0, "y": 68.0, "width": 274.0, "height": 34.0},
                "product_title": {"x": 20.0, "y": 94.0, "width": 274.0, "height": 42.0},
                "overview": {"x": 308.0, "y": 66.0, "width": 262.0, "height": 500.0},
                "product_description": {"x": 20.0, "y": 558.0, "width": 252.0, "height": 86.0},
                "application_area": {"x": 308.0, "y": 558.0, "width": 262.0, "height": 46.0},
                "features": {"x": 20.0, "y": 655.0, "width": 274.0, "height": 84.0},
                "qualifications": {"x": 22.0, "y": 482.0, "width": 258.0, "height": 64.0},
                "warranty": {"x": 308.0, "y": 620.0, "width": 262.0, "height": 120.0}
            },
            "pages": {
                "page_2": {
                    "product_specifications": {"x": 42, "y": 108, "width": 528, "height": 172},
                    "ordering_information": {"x": 42, "y": 284, "width": 528, "height": 58},
                    "photometrics": {"x": 42, "y": 344, "width": 528, "height": 138},
                    "performance_data": {"x": 42, "y": 494, "width": 528, "height": 118}
                },
                "page_3": {
                    "dimensions": {"x": 42, "y": 108, "width": 528, "height": 356},
                    "epa_specs": {"x": 42, "y": 474, "width": 528, "height": 222}
                },
                "page_4": {
                    "wiring_diagram": {"x": 42, "y": 108, "width": 252, "height": 188},
                    "surface_mounting": {"x": 318, "y": 108, "width": 252, "height": 188},
                    "accessories": {"x": 42, "y": 320, "width": 528, "height": 252}
                }
            }
        },

        "images": initial_images,
    }
    
    return form_data


def _create_pdf_response(data, finalize=False):
    """Generate either a draft preview or a finalized downloadable PDF."""
    if not data:
        return jsonify({"error": "No data provided"}), 400

    session_id = data.get('session_id')
    form_data = data.get('form_data')
    images = data.get('images', {})

    if session_id and session_id in extracted_sessions:
        session = extracted_sessions[session_id]
        tds_data = session['tds_data']
    else:
        tds_data = IKIOTDSData()

    if form_data:
        tds_data = update_tds_from_form(tds_data, form_data, images)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c for c in tds_data.product_name if c.isalnum() or c in " -_").strip()
    safe_name = safe_name.replace(" ", "_")[:30] or "TDS"
    prefix = "TDS" if finalize else "PREVIEW"
    output_filename = f"{prefix}_{safe_name}_{timestamp}.pdf"
    output_path = str(OUTPUT_DIR / output_filename)

    result_path = generate_tds(tds_data, output_path, open_after=False)
    preview_image = _render_pdf_preview(result_path)
    preview_pages = _render_pdf_pages(result_path)

    if finalize and session_id and session_id in extracted_sessions:
        del extracted_sessions[session_id]

    payload = {
        "success": True,
        "filename": output_filename,
        "download_url": f"/api/download/{output_filename}",
        "preview_image": preview_image,
        "preview_pages": preview_pages,
    }
    if not finalize:
        payload["preview_only"] = True
    return jsonify(payload)


@app.route('/api/preview-draft', methods=['POST'])
def preview_tds_api():
    """Generate a draft preview without clearing the extraction session."""
    try:
        return _create_pdf_response(request.json, finalize=False)
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route('/api/generate', methods=['POST'])
def generate_tds_api():
    """Generate the final TDS PDF from edited form data."""
    try:
        return _create_pdf_response(request.json, finalize=True)
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route('/api/generate-copy', methods=['POST'])
def generate_copy_api():
    """Generate user-requested description/features copy with configurable limits."""
    try:
        data = request.json or {}
        session_id = data.get("session_id")
        field = _clean_value(data.get("field")).lower()
        form_data = data.get("form_data", {}) or {}
        word_limit = data.get("word_limit")
        item_count = data.get("item_count")

        if not session_id or session_id not in extracted_sessions:
            return jsonify({"error": "Invalid or expired session"}), 400
        if field not in {"description", "features"}:
            return jsonify({"error": "Unsupported content field"}), 400

        generated = _generate_ai_copy(
            extracted_sessions[session_id],
            form_data,
            field=field,
            word_limit=word_limit,
            item_count=item_count,
        )
        return jsonify({"success": True, **generated})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500




def _auto_extract_sample_assets(sample_pdf_path: str):
    """Extract product image and certification badges from sample PDF using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
        from PIL import Image
        import io
    except Exception:
        return None

    if not sample_pdf_path or not Path(sample_pdf_path).exists():
        return None

    try:
        doc = fitz.open(sample_pdf_path)
        page = doc[0]
        # Render page at 2x for better crop quality
        zoom = 2.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')

        # Product image rect (top-left origin coords)
        product_rect = (276.3, 236.2, 570.1, 392.2)
        prod = img.crop((int(product_rect[0]*zoom), int(product_rect[1]*zoom), int(product_rect[2]*zoom), int(product_rect[3]*zoom)))
        prod_bytes = io.BytesIO()
        prod.save(prod_bytes, format='PNG')

        # Badge rects (4 icons) based on template curve positions
        badge_rects = [
            (426.6, 176.1, 452.7, 202.2),
            (457.3, 176.1, 483.4, 202.2),
            (488.0, 175.9, 514.1, 202.0),
            (518.7, 175.9, 544.8, 202.0),
        ]
        badge_bytes = []
        for rect in badge_rects:
            crop = img.crop((int(rect[0]*zoom), int(rect[1]*zoom), int(rect[2]*zoom), int(rect[3]*zoom)))
            buf = io.BytesIO()
            crop.save(buf, format='PNG')
            badge_bytes.append(buf.getvalue())

        doc.close()
        return {
            'product_image': prod_bytes.getvalue(),
            'badges': badge_bytes,
        }
    except Exception:
        return None

def update_tds_from_form(tds_data, form_data, images):
    """Update TDS data structure from edited form data"""
    form_images = form_data.get('images', {})
    merged_images = {}
    if isinstance(form_images, dict):
        merged_images.update(form_images)
    if isinstance(images, dict):
        merged_images.update(images)
    
    # Header / Overview
    header = form_data.get('header', {})
    tds_data.product_name = header.get('product_name', tds_data.product_name)
    tds_data.product_title = header.get('product_title', tds_data.product_title)
    tds_data.product_description = header.get('product_overview', tds_data.product_description)
    tds_data.category_path = header.get('category_path', tds_data.category_path)
    tds_data.product_category = header.get('category', header.get('category_path', tds_data.product_category))
    tds_data.project_name = header.get('project_name', tds_data.project_name)
    tds_data.catalog_number = header.get('catalog_number', tds_data.catalog_number)
    tds_data.model_number = tds_data.catalog_number or header.get('catalog_number', tds_data.model_number)
    tds_data.item_sku = header.get('item_sku', tds_data.item_sku)
    tds_data.fixture_schedule = header.get('fixture_schedule', tds_data.fixture_schedule)
    tds_data.issue_date = header.get('issue_date', tds_data.issue_date)
    description_from_form = False
    features_from_form = False
    application_from_form = False

    # Key specs (sidebar)
    key_specs = form_data.get('key_specs', {})
    tds_data.wattage = key_specs.get('power_selectable', tds_data.wattage)
    tds_data.input_voltage = key_specs.get('voltage', tds_data.input_voltage)
    tds_data.input_current = key_specs.get('current', tds_data.input_current)
    tds_data.efficacy = key_specs.get('efficacy', tds_data.efficacy)
    tds_data.cct = key_specs.get('cct_selectable', tds_data.cct)
    tds_data.lumens = key_specs.get('lumen_output', tds_data.lumens)
    tds_data.cri = key_specs.get('cri', tds_data.cri)
    tds_data.light_distribution = key_specs.get('light_distribution', tds_data.light_distribution)
    tds_data.ip_rating = key_specs.get('ip_rating', tds_data.ip_rating)
    tds_data.ik_rating = key_specs.get('ik_rating', tds_data.ik_rating)

    # Features
    raw_features = form_data.get('features', tds_data.features)
    if isinstance(raw_features, list):
        tds_data.features = [str(item).strip() for item in raw_features if str(item).strip()]
        features_from_form = 'features' in form_data
    elif isinstance(raw_features, str):
        feature_lines = []
        for line in raw_features.replace('<br>', '\n').replace('</li>', '\n').splitlines():
            cleaned = _clean_value(line.replace('<li>', '').replace('</ul>', '').replace('<ul>', ''))
            if cleaned:
                feature_lines.append(cleaned.lstrip("-• ").strip())
        if feature_lines:
            tds_data.features = feature_lines
            features_from_form = True

    # Qualifications
    qualifications = form_data.get('qualifications', {})
    if isinstance(qualifications, dict):
        tds_data.qualifications = qualifications.get('text', tds_data.qualifications)

    product_description = form_data.get('product_description', {})
    if isinstance(product_description, dict) and product_description.get('text'):
        tds_data.product_description = product_description.get('text', tds_data.product_description)
        description_from_form = True

    application_area = form_data.get('application_area', {})
    if isinstance(application_area, dict) and application_area.get('text'):
        tds_data.applications = [item.strip() for item in application_area.get('text', '').split(',') if item.strip()]
        application_from_form = True

    if not features_from_form:
        tds_data.features = _polish_features_for_layout(tds_data.features, {
            "power": tds_data.wattage,
            "voltage": tds_data.input_voltage,
            "cct": tds_data.cct,
            "ip rating": tds_data.ip_rating,
            "ik rating": tds_data.ik_rating,
            "efficacy": tds_data.efficacy,
            "housing": getattr(tds_data, "housing", ""),
        })

    if not description_from_form:
        tds_data.product_description = _polish_description_for_layout(
            tds_data.product_name,
            tds_data.product_category,
            tds_data.features,
            {
                "power": tds_data.wattage,
                "voltage": tds_data.input_voltage,
                "cct": tds_data.cct,
                "ip rating": tds_data.ip_rating,
                "ik rating": tds_data.ik_rating,
                "efficacy": tds_data.efficacy,
                "housing": getattr(tds_data, "housing", ""),
            },
            ", ".join(getattr(tds_data, "applications", []) or []),
        )

    if not application_from_form and getattr(tds_data, "applications", None):
        tds_data.applications = [_rewrite_application_text(", ".join(tds_data.applications or []), tds_data.product_category)]

    # Warranty
    warranty = form_data.get('warranty', {})
    tds_data.warranty_years = warranty.get('years', tds_data.warranty_years)
    if warranty.get('years'):
        tds_data.warranty = warranty.get('years', tds_data.warranty)
    tds_data.warranty_limitation = warranty.get('limitation', tds_data.warranty_limitation)

    # Product specifications (page 2)
    product_specs = form_data.get('product_specs', {})
    tds_data.power_factor = product_specs.get('power_factor', tds_data.power_factor)
    tds_data.thd = product_specs.get('thd', tds_data.thd)
    tds_data.beam_angle = product_specs.get('beam_angle', tds_data.beam_angle)
    tds_data.dimming = product_specs.get('dimming_control', tds_data.dimming)
    tds_data.operating_temp = product_specs.get('operating_temperature', tds_data.operating_temp)
    tds_data.suitable_location = product_specs.get('suitable_location', tds_data.suitable_location)
    tds_data.ip_rating = product_specs.get('ip_rating', tds_data.ip_rating)
    tds_data.ik_rating = product_specs.get('ik_rating', tds_data.ik_rating)
    tds_data.lifespan = product_specs.get('average_life', tds_data.lifespan)
    tds_data.warranty_years = product_specs.get('warranty_years', tds_data.warranty_years)
    tds_data.led_light_source = product_specs.get('led_light_source', tds_data.led_light_source)
    tds_data.housing_material = product_specs.get('housing', tds_data.housing_material)
    tds_data.lens_material = product_specs.get('cover_material_lens', tds_data.lens_material)
    tds_data.diffuser = product_specs.get('diffuser', tds_data.diffuser)
    tds_data.power_supply = product_specs.get('base_power_supply', tds_data.power_supply)
    tds_data.finish = product_specs.get('finish', tds_data.finish)

    # Performance data table
    from data_mapper import TDSSpecificationTable, TDSAccessory
    performance_table = form_data.get('performance_table', {})
    if performance_table.get('rows'):
        tds_data.performance_table = TDSSpecificationTable(
            title="Performance Data",
            headers=performance_table.get('headers', []),
            rows=performance_table.get('rows', [])
        )

    ordering_information = form_data.get('ordering_information', {})
    if ordering_information.get('rows'):
        headers = ordering_information.get('headers', [])
        subheaders = ordering_information.get('subheaders', [])
        groups = ordering_information.get('groups', [])
        rows = ordering_information.get('rows', [])
        tds_data.ordering_info = {
            "headers": headers,
            "subheaders": subheaders,
            "groups": groups,
            "rows": rows,
        }
        if getattr(tds_data, "ordering_structure", None):
            try:
                tds_data.ordering_structure.components = []
            except Exception:
                pass

    variant_details = form_data.get('variant_details', [])
    if isinstance(variant_details, list):
        overview_rows = []
        for item in variant_details:
            if not isinstance(item, dict):
                continue
            label = _clean_value(item.get('label'))
            value = _clean_value(item.get('value'))
            if label and value:
                overview_rows.append([label, value])
        tds_data.overview_rows = overview_rows

    # Dimensions
    dimensions = form_data.get('dimensions', {})
    tds_data.product_length = dimensions.get('product_length', tds_data.product_length)
    tds_data.product_width = dimensions.get('product_width', tds_data.product_width)
    tds_data.product_height = dimensions.get('product_height', tds_data.product_height)
    tds_data.wire_length = dimensions.get('wire_length', tds_data.wire_length)
    tds_data.net_weight = dimensions.get('net_weight', tds_data.net_weight)
    tds_data.slip_fitter_length = dimensions.get('slip_fitter_length', tds_data.slip_fitter_length)
    tds_data.slip_fitter_width = dimensions.get('slip_fitter_width', tds_data.slip_fitter_width)
    tds_data.slip_fitter_height = dimensions.get('slip_fitter_height', tds_data.slip_fitter_height)
    tds_data.slip_fitter_weight = dimensions.get('slip_fitter_weight', tds_data.slip_fitter_weight)

    # EPA table
    epa_table = form_data.get('epa_table', {})
    if epa_table.get('rows'):
        tds_data.epa_table = TDSSpecificationTable(
            title="EPA Specifications",
            headers=epa_table.get('headers', []),
            rows=epa_table.get('rows', [])
        )

    # Certifications (optional legacy)
    if form_data.get('certifications'):
        tds_data.certifications = form_data.get('certifications', tds_data.certifications)

    section_headings = form_data.get('section_headings', {})
    if isinstance(section_headings, dict):
        tds_data.section_headings = {
            str(key): str(value).strip()
            for key, value in section_headings.items()
            if str(value).strip()
        }

    visual_layout = form_data.get('visual_layout', {})
    if isinstance(visual_layout, dict):
        tds_data.layout_overrides = visual_layout

    # Keep certification badges in sync with the current qualifications/features form state.
    _refresh_certification_badges(tds_data, form_data)
    
    # IMPORTANT: NEVER use vendor badges from sample PDF - always use standard badges from images folder
    # Only use product images from vendor PDF, NOT certification badges
    # Certification badges are ALWAYS loaded from images folder via Image Asset Manager
    
    # Auto-extract product image from sample PDF if not provided (but NOT badges)
    sample_pdf = str(Path(__file__).parent / "IKIO Spec Sheet for Web Single SKU.pdf")
    auto_assets = _auto_extract_sample_assets(sample_pdf)
    if auto_assets:
        has_vendor_product = any(
            _clean_value(item.get('image_type', '')).lower() == 'product'
            for item in (getattr(tds_data, 'extracted_images', []) or [])
            if isinstance(item, dict)
        )
        if 'product_image' not in merged_images and not getattr(tds_data, 'product_images', None) and not has_vendor_product:
            tds_data.product_images = [auto_assets['product_image']]
        # DO NOT use badges from sample PDF - always use standard badges from images folder
        # tds_data.certification_badges should already be set by data_mapper using Image Asset Manager

    # Handle image assignments
    if merged_images:
        # Certification badges (optional)
        badge_slots = ['cert_badge_1', 'cert_badge_2', 'cert_badge_3', 'cert_badge_4']
        badges = []
        for slot in badge_slots:
            if not merged_images.get(slot):
                continue
            img_data = merged_images[slot]
            if isinstance(img_data, str):
                if img_data.startswith('data:'):
                    img_data = img_data.split(',')[1]
                img_bytes = base64.b64decode(img_data) if img_data else None
                if img_bytes:
                    badges.append(img_bytes)
        if badges:
            tds_data.certification_badges = badges

        # Product image
        if 'product_image' in merged_images:
            img_data = merged_images.get('product_image')
            if isinstance(img_data, str):
                if img_data.startswith('data:'):
                    img_data = img_data.split(',')[1]
                tds_data.product_images = [base64.b64decode(img_data)] if img_data else []
            elif not img_data:
                tds_data.product_images = []
        
        # Dimension diagram
        if 'dimension_diagram' in merged_images:
            img_data = merged_images.get('dimension_diagram')
            if isinstance(img_data, str):
                if img_data.startswith('data:'):
                    img_data = img_data.split(',')[1]
                tds_data.dimension_diagram_data = base64.b64decode(img_data) if img_data else None
            elif not img_data:
                tds_data.dimension_diagram_data = None

        # Photometrics diagram
        if 'photometric_diagram' in merged_images:
            img_data = merged_images.get('photometric_diagram')
            if isinstance(img_data, str):
                if img_data.startswith('data:'):
                    img_data = img_data.split(',')[1]
                tds_data.photometrics_diagram_data = base64.b64decode(img_data) if img_data else None
            elif not img_data:
                tds_data.photometrics_diagram_data = None

        if 'wiring_diagram' in merged_images:
            img_data = merged_images.get('wiring_diagram')
            if isinstance(img_data, str):
                if img_data.startswith('data:'):
                    img_data = img_data.split(',')[1]
                img_bytes = base64.b64decode(img_data) if img_data else None
                tds_data.wiring_diagrams = [{"image_data": img_bytes, "type": "wiring"}] if img_bytes else []
            elif not img_data:
                tds_data.wiring_diagrams = []

        if 'surface_mounting' in merged_images:
            img_data = merged_images.get('surface_mounting')
            if isinstance(img_data, str):
                if img_data.startswith('data:'):
                    img_data = img_data.split(',')[1]
                img_bytes = base64.b64decode(img_data) if img_data else None
                tds_data.mounting_options = [TDSAccessory(name="Surface Mounting", image_data=img_bytes)] if img_bytes else []
            elif not img_data:
                tds_data.mounting_options = []

        # Accessory images (optional)
        accessory_slots = ['accessory_image_1', 'accessory_image_2', 'accessory_image_3', 'accessory_image_4']
        for idx, slot in enumerate(accessory_slots):
            if not merged_images.get(slot):
                continue
            img_data = merged_images[slot]
            if isinstance(img_data, str):
                if img_data.startswith('data:'):
                    img_data = img_data.split(',')[1]
                img_bytes = base64.b64decode(img_data) if img_data else None
                if img_bytes and idx < len(tds_data.accessories):
                    tds_data.accessories[idx].image_data = img_bytes
    
    return tds_data


@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download generated PDF file"""
    try:
        return send_from_directory(
            OUTPUT_DIR,
            filename,
            as_attachment=True,
            mimetype='application/pdf'
        )
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404


@app.route('/api/recent', methods=['GET'])
def get_recent_files():
    """Get list of recently generated TDS files"""
    try:
        pdf_files = sorted(
            Path(OUTPUT_DIR).glob("*.pdf"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )[:20]
        
        files = []
        for pdf_file in pdf_files:
            stat = pdf_file.stat()
            files.append({
                "filename": pdf_file.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "download_url": f"/api/download/{pdf_file.name}"
            })
        
        return jsonify({"files": files})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/preview/<filename>', methods=['GET'])
def get_preview(filename):
    """Get preview image of a PDF file"""
    try:
        pdf_path = OUTPUT_DIR / filename
        if not pdf_path.exists():
            return jsonify({"error": "File not found"}), 404
        
        import fitz
        doc = fitz.open(str(pdf_path))
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        img_bytes = pix.tobytes("png")
        doc.close()
        
        return jsonify({
            "preview_image": base64.b64encode(img_bytes).decode('utf-8')
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/delete/<filename>', methods=['DELETE'])
def delete_file(filename):
    """Delete a generated PDF file"""
    try:
        pdf_path = OUTPUT_DIR / filename
        if pdf_path.exists():
            os.unlink(pdf_path)
            return jsonify({"success": True})
        else:
            return jsonify({"error": "File not found"}), 404
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai-image/generate', methods=['POST'])
def generate_ai_image():
    """
    Generate an AI image using Pollinations.ai (100% FREE, no API key needed)
    Returns base64 encoded image
    """
    try:
        import requests
        
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        prompt = data.get('prompt', '')
        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400
        
        # Get optional parameters
        width = data.get('width', 512)
        height = data.get('height', 512)
        seed = data.get('seed', None)
        style = data.get('style', '')
        
        # Build full prompt with style if provided
        full_prompt = f"{prompt}, {style}" if style else prompt
        
        # Build Pollinations.ai URL (100% free, no API key)
        encoded_prompt = requests.utils.quote(full_prompt)
        params = f"width={width}&height={height}&nologo=true"
        if seed:
            params += f"&seed={seed}"
        
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?{params}"
        
        # Fetch the image
        response = requests.get(image_url, timeout=60)
        if response.status_code != 200:
            return jsonify({"error": f"Failed to generate image: {response.status_code}"}), 500
        
        # Convert to base64
        img_base64 = base64.b64encode(response.content).decode('utf-8')
        
        return jsonify({
            "success": True,
            "image": img_base64,
            "prompt": full_prompt,
            "width": width,
            "height": height,
        })
    
    except requests.exceptions.Timeout:
        return jsonify({"error": "Image generation timed out. Please try again."}), 504
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai-image/remove-background', methods=['POST'])
def remove_background():
    """
    Remove background from an image using rembg library (offline, free)
    Falls back to simple white background if rembg not available
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        image_base64 = data.get('image')
        if not image_base64:
            return jsonify({"error": "Image data is required"}), 400
        
        # Decode base64 image
        image_data = base64.b64decode(image_base64)
        
        try:
            # Try to use rembg for background removal
            from rembg import remove
            from PIL import Image
            import io
            
            input_image = Image.open(io.BytesIO(image_data))
            output_image = remove(input_image)
            
            # Convert back to base64
            buffered = io.BytesIO()
            output_image.save(buffered, format="PNG")
            result_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            return jsonify({
                "success": True,
                "image": result_base64,
            })
        except ImportError:
            # rembg not installed, return original with message
            return jsonify({
                "success": False,
                "error": "Background removal library not installed. Install with: pip install rembg",
                "image": image_base64,  # Return original
            })
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/ai-image/enhance', methods=['POST'])
def enhance_image():
    """
    Enhance image quality using PIL (brightness, contrast, sharpness)
    """
    try:
        from PIL import Image, ImageEnhance
        import io
        
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        image_base64 = data.get('image')
        if not image_base64:
            return jsonify({"error": "Image data is required"}), 400
        
        # Get enhancement parameters
        brightness = data.get('brightness', 1.0)  # 1.0 = original
        contrast = data.get('contrast', 1.0)
        sharpness = data.get('sharpness', 1.0)
        
        # Decode and process image
        image_data = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_data))
        
        # Apply enhancements
        if brightness != 1.0:
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(brightness)
        
        if contrast != 1.0:
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(contrast)
        
        if sharpness != 1.0:
            enhancer = ImageEnhance.Sharpness(image)
            image = enhancer.enhance(sharpness)
        
        # Convert back to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        result_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        return jsonify({
            "success": True,
            "image": result_base64,
        })
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("Starting TDS Generator API...")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Enhanced processing available: {ENHANCED_AVAILABLE}")
    app.run(debug=True, host='0.0.0.0', port=5000)
