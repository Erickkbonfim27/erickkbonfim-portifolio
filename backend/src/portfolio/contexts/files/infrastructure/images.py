"""Photos re-encoded with Pillow (HEIC through pillow-heif)."""

import io
from dataclasses import dataclass

import pillow_heif
from PIL import Image, ImageOps, UnidentifiedImageError

from portfolio.contexts.files.domain.model import UnsupportedFileError

pillow_heif.register_heif_opener()


@dataclass(frozen=True, slots=True)
class PillowImages:
    """Upright, at most `max_side` pixels on the longest side, WebP, no metadata."""

    max_side: int = 2400
    quality: int = 82

    def to_webp(self, data: bytes) -> bytes:
        try:
            with Image.open(io.BytesIO(data)) as source:
                # Phones store the rotation in EXIF; apply it before EXIF is dropped.
                image = ImageOps.exif_transpose(source)
                if image.mode == "P":  # palette logos may carry transparency
                    image = image.convert("RGBA")
                image.thumbnail((self.max_side, self.max_side), Image.Resampling.LANCZOS)
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                out = io.BytesIO()
                # Nothing is copied over: no EXIF (GPS), no XMP, no ICC profile.
                image.save(out, "WEBP", quality=self.quality, method=6)
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise UnsupportedFileError("the image could not be read") from error
        return out.getvalue()
