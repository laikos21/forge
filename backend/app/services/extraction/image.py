"""Image / screenshot extraction.

Always available: dimensions, format, EXIF (including capture date and camera).
Optional: OCR text, when *both* the ``pytesseract`` package and a Tesseract
binary are present. FORGE never requires either - an image without OCR is still
a first-class source that can be titled, tagged, linked and annotated.
"""

from __future__ import annotations

import datetime as dt
import io
import shutil
from dataclasses import dataclass
from functools import lru_cache

from ...lib.text import normalize_text
from .base import DocumentUnit, ExtractedMetadata, ExtractionError, ExtractionResult, assemble

EXIF_TAGS = {
    271: "camera_make",
    272: "camera_model",
    274: "orientation",
    306: "datetime",
    36867: "datetime_original",
    37377: "shutter_speed",
    33434: "exposure_time",
    34855: "iso",
    305: "software",
}


@dataclass(frozen=True, slots=True)
class OcrStatus:
    available: bool
    reason: str
    binary_path: str | None = None
    version: str | None = None


@lru_cache(maxsize=1)
def ocr_status() -> OcrStatus:
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return OcrStatus(False, "The optional 'pytesseract' package is not installed.")
    binary = shutil.which("tesseract")
    if not binary:
        return OcrStatus(False, "The Tesseract binary was not found on PATH.")
    try:
        import pytesseract

        version = str(pytesseract.get_tesseract_version())
    except Exception as exc:  # pragma: no cover - depends on local install
        return OcrStatus(False, f"Tesseract found but not usable: {exc}", binary)
    return OcrStatus(True, "Tesseract is available.", binary, version)


def reset_ocr_cache() -> None:
    ocr_status.cache_clear()


def run_ocr(data: bytes, language: str = "eng") -> str:
    status = ocr_status()
    if not status.available:
        raise ExtractionError(status.reason)
    import pytesseract
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return normalize_text(pytesseract.image_to_string(image, lang=language))


def extract_image(data: bytes, filename: str | None = None, ocr: bool = False) -> ExtractionResult:
    try:
        from PIL import ExifTags, Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ExtractionError("Pillow is not installed") from exc

    warnings: list[str] = []
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            width, height = image.size
            image_format = image.format or "unknown"
            mode = image.mode
            exif_raw = {}
            try:
                exif = image.getexif()
                exif_raw = {
                    EXIF_TAGS.get(tag, ExifTags.TAGS.get(tag, str(tag))): str(value)
                    for tag, value in exif.items()
                    if isinstance(value, str | int | float | bytes) and len(str(value)) < 300
                }
            except Exception:  # pragma: no cover - corrupt EXIF blocks
                warnings.append("EXIF block could not be read.")
    except UnidentifiedImageError as exc:
        raise ExtractionError(f"unsupported or corrupt image: {exc}") from exc
    except OSError as exc:
        raise ExtractionError(f"could not read image: {exc}") from exc

    captured: dt.date | None = None
    stamp = exif_raw.get("datetime_original") or exif_raw.get("datetime")
    if stamp:
        try:
            captured = dt.datetime.strptime(str(stamp)[:19], "%Y:%m:%d %H:%M:%S").date()
        except ValueError:
            captured = None

    description_lines = [
        f"Image: {filename or 'screenshot'}",
        f"Format: {image_format} · {width}x{height}px · mode {mode}",
    ]
    if exif_raw:
        description_lines.append(
            "EXIF: " + "; ".join(f"{k}={v}" for k, v in sorted(exif_raw.items())[:12])
        )

    ocr_text = ""
    if ocr:
        status = ocr_status()
        if status.available:
            try:
                ocr_text = run_ocr(data)
            except Exception as exc:
                warnings.append(f"OCR failed: {exc}")
        else:
            warnings.append(f"OCR requested but unavailable. {status.reason}")

    units = [
        DocumentUnit(
            kind="whole",
            text="\n".join(description_lines),
            title="Image metadata",
            locator={"region": "metadata"},
        )
    ]
    if ocr_text.strip():
        units.append(
            DocumentUnit(
                kind="section",
                text=ocr_text,
                title="OCR text",
                locator={"region": "ocr", "engine": "tesseract"},
            )
        )
    else:
        warnings.append(
            "No text layer stored for this image. Add a note or enable OCR in Settings "
            "if you need it to be searchable by content."
        )

    metadata = ExtractedMetadata(
        title=filename or "Screenshot",
        published_on=captured,
        page_count=1,
    )
    metadata.extra.update(
        {
            "width": width,
            "height": height,
            "format": image_format,
            "mode": mode,
            "exif": exif_raw,
            "ocr_applied": bool(ocr_text.strip()),
        }
    )
    method = "image+ocr" if ocr_text.strip() else "image_metadata"
    return assemble(units, method, metadata, warnings)
