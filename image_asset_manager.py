"""
Image Asset Manager
Manages standard certification badges, warranty icons, and other standard images
from the images folder for use in TDS generation.
"""
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image as PILImage
import io

from config import BASE_DIR
from product_knowledge import get_icon_knowledge

IMAGES_DIR = BASE_DIR / "images"


class ImageAssetManager:
    """
    Manages standard images (certifications, warranties, icons) from the images folder.
    Provides intelligent matching of vendor certifications to standard badge images.
    """
    
    def __init__(self, images_dir: Optional[Path] = None):
        self.images_dir = images_dir or IMAGES_DIR
        self.standard_images: Dict[str, bytes] = {}
        self._load_standard_images()
    
    def _load_standard_images(self):
        """Load all PNG images from the images directory"""
        if not self.images_dir.exists():
            print(f"Warning: Images directory not found: {self.images_dir}")
            return
        
        for img_file in self.images_dir.glob("*.png"):
            try:
                with open(img_file, 'rb') as f:
                    img_bytes = f.read()
                    # Store by filename (without extension) for easy lookup
                    key = img_file.stem.lower()
                    self.standard_images[key] = img_bytes
                    print(f"Loaded standard image: {img_file.name}")
            except Exception as e:
                print(f"Warning: Could not load {img_file.name}: {e}")
    
    def get_warranty_image(self, years: Optional[int] = None) -> Optional[bytes]:
        """
        Get warranty image based on warranty years.
        Returns the most appropriate warranty badge.
        """
        if years is None:
            # Default to 5-year if not specified
            years = 5
        
        # Try to find matching warranty image
        if years >= 10:
            # Try 10-year warranty images
            for key in ['10-year-warranty-200', '10-year-warranty']:
                if key in self.standard_images:
                    return self.standard_images[key]
        elif years >= 5:
            # Try 5-year warranty
            if '5-year-warranty' in self.standard_images:
                return self.standard_images['5-year-warranty']
        
        # Fallback to any warranty image
        for key in self.standard_images.keys():
            if 'warranty' in key:
                return self.standard_images[key]
        
        return None
    
    def get_certification_badges(self, certifications: List[str]) -> List[bytes]:
        """
        Match vendor certifications to standard badge images.
        Returns list of badge image bytes in order of relevance.
        """
        badges = []
        cert_lower = [" ".join(str(c or "").lower().split()) for c in certifications]
        matched_keys = set()
        import re

        search_text = " | ".join(cert_lower)

        # Knowledge-base driven matching so qualification text can map to the
        # correct standard icon even when the wording varies by source.
        for entry in sorted(get_icon_knowledge(), key=lambda item: item.get("priority", 0), reverse=True):
            asset_key = str(entry.get("asset", "")).lower()
            if not asset_key or asset_key in matched_keys or asset_key not in self.standard_images:
                continue

            aliases = [" ".join(str(alias or "").lower().split()) for alias in entry.get("aliases", [])]
            if any(alias and alias in search_text for alias in aliases):
                badges.append(self.standard_images[asset_key])
                matched_keys.add(asset_key)

        # Mapping of certification keywords to image filenames
        cert_mapping = {
            'dlc': ['dlc-premium', 'dlc-standred'],
            'premium': ['dlc-premium'],
            'energy star': ['energy-star'],
            'etl': ['etl'],
            'ul': ['ul'],
            'rohs': ['rohs'],
            'ip65': ['ip65'],
            'ip66': ['ip65'],  # Use IP65 image for IP66
            'ip67': ['ip65'],  # Use IP65 image for IP67
            'ip68': ['ip65'],  # Use IP65 image for IP68
            'ip': ['ip65'],  # Generic IP rating uses IP65 badge
        }
        
        # First, check for IP ratings in format "IP65", "IP 65", "65" etc.
        for cert in cert_lower:
            ip_match = re.search(r'ip\s*(\d+)', cert)
            if ip_match:
                ip_num = ip_match.group(1)
                if ip_num in ['65', '66', '67', '68']:
                    ip_badge = self.get_image_by_name('IP65')
                    if ip_badge and 'ip65' not in matched_keys:
                        badges.append(ip_badge)
                        matched_keys.add('ip65')
                        break  # Only add one IP badge
        
        # Match certifications to images
        for cert in cert_lower:
            for keyword, image_keys in cert_mapping.items():
                if keyword in cert:
                    for img_key in image_keys:
                        if img_key in self.standard_images and img_key not in matched_keys:
                            badges.append(self.standard_images[img_key])
                            matched_keys.add(img_key)
                            break
        
        # Also check for feature icons
        feature_mapping = {
            'cct': 'cct-selectable',
            'selectable': 'cct-selectable',
            'dimmable': 'dimmable',
            'dimming': 'dimmable',
            'power': 'power-selectable',
            'sensor': 'sensors',
            'motion': 'sensors',
        }
        
        for cert in cert_lower:
            for keyword, img_key in feature_mapping.items():
                if keyword in cert and img_key in self.standard_images:
                    if img_key not in matched_keys:
                        badges.append(self.standard_images[img_key])
                        matched_keys.add(img_key)
                        break
        
        return badges[:4]  # Return max 4 badges

    def get_feature_icons(self, features: List[str]) -> List[bytes]:
        """
        Extract feature icons based on product features.
        """
        icons = []
        features_lower = [" ".join(str(f or "").lower().split()) for f in features]
        matched_keys = set()
        search_text = " | ".join(features_lower)

        for entry in sorted(get_icon_knowledge(), key=lambda item: item.get("priority", 0), reverse=True):
            asset_key = str(entry.get("asset", "")).lower()
            if not asset_key or asset_key in matched_keys or asset_key not in self.standard_images:
                continue
            aliases = [" ".join(str(alias or "").lower().split()) for alias in entry.get("aliases", [])]
            if any(alias and alias in search_text for alias in aliases):
                icons.append(self.standard_images[asset_key])
                matched_keys.add(asset_key)
                if len(icons) >= 4:
                    return icons
        
        feature_mapping = {
            'dimmable': 'dimmable',
            'dimming': 'dimmable',
            'cct': 'cct-selectable',
            'selectable': 'cct-selectable',
            'power': 'power-selectable',
            'sensor': 'sensors',
            'motion': 'sensors',
        }
        
        for feature in features_lower:
            for keyword, img_key in feature_mapping.items():
                if keyword in feature and img_key in self.standard_images:
                    if img_key not in matched_keys:
                        icons.append(self.standard_images[img_key])
                        matched_keys.add(img_key)
                        break
        
        return icons
    
    def get_all_badges(self) -> Dict[str, bytes]:
        """Get all available standard images"""
        return self.standard_images.copy()
    
    def get_image_by_name(self, name: str) -> Optional[bytes]:
        """Get a specific image by name (case-insensitive)"""
        name_lower = name.lower().replace('.png', '')
        return self.standard_images.get(name_lower)
    
    def resize_image(self, image_bytes: bytes, max_width: int = 200, max_height: int = 200) -> bytes:
        """Resize an image to fit within specified dimensions while maintaining aspect ratio"""
        try:
            img = PILImage.open(io.BytesIO(image_bytes))
            img.thumbnail((max_width, max_height), PILImage.Resampling.LANCZOS)
            
            output = io.BytesIO()
            img.save(output, format='PNG')
            return output.getvalue()
        except Exception as e:
            print(f"Warning: Could not resize image: {e}")
            return image_bytes


# Global instance
_asset_manager: Optional[ImageAssetManager] = None


def get_asset_manager() -> ImageAssetManager:
    """Get or create the global image asset manager instance"""
    global _asset_manager
    if _asset_manager is None:
        _asset_manager = ImageAssetManager()
    return _asset_manager
