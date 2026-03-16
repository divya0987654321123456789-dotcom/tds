from __future__ import annotations

import re
from typing import Any


ICON_KNOWLEDGE_BASE: list[dict[str, Any]] = [
    {
        "asset": "DLC-Premium",
        "aliases": ["dlc premium", "dlc listed premium", "dlc"],
        "priority": 100,
    },
    {
        "asset": "ETL",
        "aliases": ["etl", "etl listed", "cetl", "cetlus", "cetlus listed"],
        "priority": 90,
    },
    {
        "asset": "RoHS",
        "aliases": ["rohs", "rohs compliant"],
        "priority": 80,
    },
    {
        "asset": "IP65",
        "aliases": ["ip65", "ip66", "ip67", "ip68", "weatherproof", "wet location"],
        "priority": 70,
    },
    {
        "asset": "UL",
        "aliases": ["ul", "ul listed", "culus", "c ul us", "ul us"],
        "priority": 60,
    },
    {
        "asset": "Energy-Star",
        "aliases": ["energy star"],
        "priority": 50,
    },
    {
        "asset": "CCT-Selectable",
        "aliases": ["cct selectable", "selectable cct", "multi cct", "tunable white"],
        "priority": 40,
    },
    {
        "asset": "Power-Selectable",
        "aliases": ["power selectable", "selectable wattage", "multi watt"],
        "priority": 30,
    },
    {
        "asset": "Dimmable",
        "aliases": ["dimmable", "dimming", "0-10v", "dmx"],
        "priority": 20,
    },
    {
        "asset": "Sensors",
        "aliases": ["sensor", "motion sensor", "sensor ready"],
        "priority": 10,
    },
]


PRODUCT_KNOWLEDGE_BASE: list[dict[str, Any]] = [
    {
        "id": "fl47_exiona",
        "series": ["FL47"],
        "models": ["FL47-480", "FL47-600"],
        "keywords": [
            "flood light",
            "sports light",
            "stadium",
            "soccer field",
            "rugby field",
            "baseball field",
        ],
        "header": {
            "product_name": "Exiona",
            "product_title": "Stadium Flood Light",
            "category": "Outdoor Light",
            "category_path": "OUTDOOR LIGHTS | FLOOD LIGHTS",
        },
        "qualifications": ["DLC Premium", "ETL", "RoHS", "IP65"],
        "warranty": {
            "years": "10 years",
            "text": "10-year limited warranty covering defects in materials and workmanship under normal use and proper installation.",
        },
    }
]


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _collect_text_parts(vendor_data: Any = None, tds_data: Any = None, form_data: Any = None) -> list[str]:
    parts: list[str] = []

    for obj in (vendor_data, tds_data):
        if not obj:
            continue
        for attr in (
            "product_name",
            "product_series",
            "product_category",
            "product_description",
            "tagline",
            "model_number",
            "catalog_number",
        ):
            parts.append(getattr(obj, attr, ""))
        parts.extend(getattr(obj, "model_numbers", []) or [])
        parts.extend(getattr(obj, "features", []) or [])
        parts.extend(getattr(obj, "applications", []) or [])
        parts.extend(getattr(obj, "certifications", []) or [])

    if isinstance(form_data, dict):
        header = form_data.get("header", {})
        qualifications = form_data.get("qualifications", {})
        parts.extend(
            [
                header.get("product_name", ""),
                header.get("product_title", ""),
                header.get("category", ""),
                header.get("category_path", ""),
                header.get("catalog_number", ""),
                header.get("product_overview", ""),
                qualifications.get("text", "") if isinstance(qualifications, dict) else "",
            ]
        )
        parts.extend(form_data.get("features", []) or [])

    return [str(part) for part in parts if str(part or "").strip()]


def _collect_series_tokens(vendor_data: Any = None, tds_data: Any = None, form_data: Any = None) -> set[str]:
    tokens: set[str] = set()

    for obj in (vendor_data, tds_data):
        if not obj:
            continue
        for value in (
            getattr(obj, "product_series", ""),
            getattr(obj, "product_name", ""),
            getattr(obj, "model_number", ""),
            getattr(obj, "catalog_number", ""),
        ):
            text = str(value or "")
            for match in re.findall(r"\b[A-Z]{2,}\d{2,}\b", text.upper()):
                tokens.add(match.lower())
        for model in getattr(obj, "model_numbers", []) or []:
            for match in re.findall(r"\b[A-Z]{2,}\d{2,}\b", str(model).upper()):
                tokens.add(match.lower())

    if isinstance(form_data, dict):
        header = form_data.get("header", {})
        for value in (
            header.get("catalog_number", ""),
            header.get("subcategory", ""),
            header.get("product_name", ""),
        ):
            for match in re.findall(r"\b[A-Z]{2,}\d{2,}\b", str(value).upper()):
                tokens.add(match.lower())

    return tokens


def _collect_model_tokens(vendor_data: Any = None, tds_data: Any = None, form_data: Any = None) -> set[str]:
    tokens: set[str] = set()

    for obj in (vendor_data, tds_data):
        if not obj:
            continue
        for value in (getattr(obj, "model_number", ""), getattr(obj, "catalog_number", "")):
            cleaned = _normalize_text(value)
            if cleaned:
                tokens.add(cleaned)
        for model in getattr(obj, "model_numbers", []) or []:
            cleaned = _normalize_text(model)
            if cleaned:
                tokens.add(cleaned)

    if isinstance(form_data, dict):
        header = form_data.get("header", {})
        cleaned = _normalize_text(header.get("catalog_number", ""))
        if cleaned:
            tokens.add(cleaned)

    return tokens


def get_icon_knowledge() -> list[dict[str, Any]]:
    return list(ICON_KNOWLEDGE_BASE)


def match_product_profile(vendor_data: Any = None, tds_data: Any = None, form_data: Any = None) -> dict[str, Any] | None:
    search_text = " ".join(_normalize_text(part) for part in _collect_text_parts(vendor_data, tds_data, form_data))
    if not search_text:
        return None

    series_tokens = _collect_series_tokens(vendor_data, tds_data, form_data)
    model_tokens = _collect_model_tokens(vendor_data, tds_data, form_data)

    best_profile: dict[str, Any] | None = None
    best_score = 0

    for profile in PRODUCT_KNOWLEDGE_BASE:
        score = 0

        for series in profile.get("series", []) or []:
            if _normalize_text(series) in series_tokens:
                score += 10

        for model in profile.get("models", []) or []:
            normalized_model = _normalize_text(model)
            if normalized_model in model_tokens or normalized_model in search_text:
                score += 6

        keyword_hits = 0
        for keyword in profile.get("keywords", []) or []:
            if _normalize_text(keyword) and _normalize_text(keyword) in search_text:
                keyword_hits += 1
        score += min(keyword_hits, 4)

        if score > best_score:
            best_score = score
            best_profile = profile

    return best_profile if best_score >= 8 else None


def get_profile_header(profile: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(profile, dict):
        return {}
    header = profile.get("header", {})
    return header if isinstance(header, dict) else {}


def get_profile_badge_terms(profile: dict[str, Any] | None) -> list[str]:
    if not isinstance(profile, dict):
        return []
    values = profile.get("qualifications", [])
    return [str(value).strip() for value in values if str(value).strip()]


def get_profile_warranty(profile: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(profile, dict):
        return {}
    warranty = profile.get("warranty", {})
    return warranty if isinstance(warranty, dict) else {}
