---
name: image-verification
description: Verify images and documents — metadata extraction, geolocation from EXIF, provenance checks, manipulation red flags.
---

# Image & Document Verification

## Methodology

1. **Metadata** — save the file locally, then `extract_metadata`:
   - EXIF DateTimeOriginal vs. claimed date.
   - GPS coordinates → plug into a map. No GPS ≠ fake (social platforms strip EXIF),
     but GPS present and contradicting the claim = strong finding.
   - Software field: "Adobe Photoshop" is normal for press photos; note it, don't
     over-read it. Camera make/model should be consistent across a source's images.
2. **Provenance** — `web_search` for the image context: who published it first?
   `wayback_snapshots` on the hosting page for the earliest archived version.
3. **Document forensics** — PDFs/DOCX: author, creator tool, creation/modification
   timestamps. A "2019 report" whose PDF says created 2024 in Word 16 = finding.
4. **Cross-source** — weather, shadows, terrain, signage from the claimed location
   and date should agree. Use `web_search` to corroborate details.

## Red flags (record as observations, with confidence)

- Metadata stripped *and* source refuses to provide original.
- Inconsistent shadows/sun angle for claimed time.
- Text/signage in wrong language or script for claimed location.
- Compression artifacts localized around the subject (possible compositing).

## Rules

- State what the evidence shows and what it does not. Absence of EXIF is not
  evidence of manipulation.
- Never alter the original file; work on copies.
