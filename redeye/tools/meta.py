"""File metadata extraction: images (EXIF/GPS), PDFs, Office documents."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..config import Config
from .base import ToolRegistry, ToolResult


def register(registry: ToolRegistry, cfg: Config) -> None:

    @registry.tool(
        name="extract_metadata",
        description=(
            "Extract hidden metadata from a local file: EXIF + GPS coordinates from images, "
            "author/toolchain from PDFs, author/company/revision info from Office documents. "
            "File must be on the local filesystem."
        ),
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Local file path"}},
            "required": ["path"],
        },
    )
    def extract_metadata(path: str) -> ToolResult:
        p = Path(path).expanduser()
        if not p.exists() or not p.is_file():
            return ToolResult.error(f"file not found: {p}")
        ext = p.suffix.lower()
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        lines = [f"Metadata for {p} ({p.stat().st_size} bytes)", f"  sha256: {sha}"]
        try:
            if ext in (".jpg", ".jpeg", ".png", ".tiff", ".heic", ".webp"):
                lines += _image_meta(p)
            elif ext == ".pdf":
                lines += _pdf_meta(p)
            elif ext in (".docx", ".xlsx", ".pptx"):
                lines += _docx_meta(p)
            else:
                lines.append(f"  (no specialized parser for {ext or 'this type'}; hash above)")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  parser error: {type(exc).__name__}: {exc}")
        return ToolResult(ok=True, content="\n".join(lines))


def _image_meta(p: Path) -> list[str]:
    out: list[str] = []
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        with Image.open(p) as img:
            out.append(f"  image: {img.format} {img.size[0]}x{img.size[1]}")
            exif = img.getexif()
            for tag_id, value in exif.items():
                name = TAGS.get(tag_id, str(tag_id))
                if name in ("Make", "Model", "DateTime", "DateTimeOriginal", "Software",
                            "LensModel", "Artist", "Copyright"):
                    out.append(f"  {name}: {value}")
    except Exception as exc:  # noqa: BLE001
        out.append(f"  PIL: {exc}")
    try:
        import exifread

        with open(p, "rb") as fh:
            tags = exifread.process_file(fh, details=False)

        def _rat(v):
            return float(v.values[0].num) / float(v.values[0].den)

        lat = tags.get("GPS GPSLatitude")
        lat_ref = tags.get("GPS GPSLatitudeRef")
        lon = tags.get("GPS GPSLongitude")
        lon_ref = tags.get("GPS GPSLongitudeRef")
        if lat and lon and lat.values and lon.values:
            la = _rat(lat.values[0]) + _rat(lat.values[1]) / 60 + _rat(lat.values[2]) / 3600
            lo = _rat(lon.values[0]) + _rat(lon.values[1]) / 60 + _rat(lon.values[2]) / 3600
            if str(lat_ref) == "S":
                la = -la
            if str(lon_ref) == "W":
                lo = -lo
            out.append(f"  GPS: {la:.6f}, {lo:.6f}  (https://www.openstreetmap.org/?mlat={la:.6f}&mlon={lo:.6f}#map=16/{la:.6f}/{lo:.6f})")
    except Exception:
        pass
    return out or ["  no EXIF metadata found"]


def _pdf_meta(p: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(p))
    out = [f"  pages: {len(reader.pages)}"]
    meta = reader.metadata or {}
    for k, v in meta.items():
        out.append(f"  {k.lstrip('/')}: {v}")
    return out


def _docx_meta(p: Path) -> list[str]:
    import docx

    doc = docx.Document(str(p))
    cp = doc.core_properties
    out = []
    for attr in ("author", "last_modified_by", "created", "modified", "title",
                 "subject", "category", "comments", "revision"):
        v = getattr(cp, attr, None)
        if v:
            out.append(f"  {attr}: {v}")
    return out or ["  no core properties set"]
