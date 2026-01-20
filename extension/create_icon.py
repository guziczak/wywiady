import os
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont
import nicegui

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from branding import BRAND_ICON, BRAND_ICON_BG, BRAND_ICON_TAG

BG = tuple(int(BRAND_ICON_BG.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
FG = (255, 255, 255)

FONT_WOFF2 = (
    Path(nicegui.__file__).parent
    / "static"
    / "fonts"
    / "0c19a63c7528cc1a.woff2"
)
LIGATURE_NAME = BRAND_ICON


def _get_ligature_codepoint(font: TTFont, ligature: str) -> int:
    cmap = {}
    for table in font["cmap"].tables:
        if table.isUnicode():
            cmap.update(table.cmap)

    glyph_to_char = {}
    glyph_to_code = {}
    for code, glyph_name in cmap.items():
        if glyph_name not in glyph_to_char:
            glyph_to_char[glyph_name] = chr(code)
            glyph_to_code[glyph_name] = code

    lig_glyph = None
    gsub = font["GSUB"].table
    for lookup in gsub.LookupList.Lookup:
        if lookup.LookupType != 4:
            continue
        for subtable in lookup.SubTable:
            if not hasattr(subtable, "ligatures"):
                continue
            for first, ligs in subtable.ligatures.items():
                for lig in ligs:
                    chars = []
                    for gname in [first] + lig.Component:
                        ch = glyph_to_char.get(gname)
                        if ch is None:
                            chars = None
                            break
                        chars.append(ch)
                    if chars is None:
                        continue
                    if "".join(chars) == ligature:
                        lig_glyph = lig.LigGlyph
                        break
                if lig_glyph:
                    break
            if lig_glyph:
                break
        if lig_glyph:
            break

    if not lig_glyph:
        raise RuntimeError(f"Ligature not found: {ligature}")

    if lig_glyph in glyph_to_code:
        return glyph_to_code[lig_glyph]

    if lig_glyph.startswith("uni"):
        return int(lig_glyph[3:], 16)

    raise RuntimeError(f"No codepoint for glyph: {lig_glyph}")


def _render_icon(size: int, ttf_path: Path, glyph_char: str) -> Image.Image:
    img = Image.new("RGBA", (size, size), BG)
    draw = ImageDraw.Draw(img)

    max_ratio = 0.82 if size >= 128 else 0.92
    max_box = int(size * max_ratio)
    font_size = size
    font_obj = None
    step = 2 if size <= 48 else 4

    while font_size > 4:
        font_obj = ImageFont.truetype(str(ttf_path), font_size)
        bbox = draw.textbbox((0, 0), glyph_char, font=font_obj)
        glyph_w = bbox[2] - bbox[0]
        glyph_h = bbox[3] - bbox[1]
        if glyph_w <= max_box and glyph_h <= max_box:
            break
        font_size -= step

    if font_obj is None:
        raise RuntimeError("Material Icons font not loaded")

    bbox = draw.textbbox((0, 0), glyph_char, font=font_obj)
    glyph_w = bbox[2] - bbox[0]
    glyph_h = bbox[3] - bbox[1]
    x = (size - glyph_w) // 2 - bbox[0]
    y = (size - glyph_h) // 2 - bbox[1]
    draw.text((x, y), glyph_char, font=font_obj, fill=FG)
    return img


font = TTFont(str(FONT_WOFF2))
codepoint = _get_ligature_codepoint(font, LIGATURE_NAME)
glyph_char = chr(codepoint)

tmp_ttf = Path(tempfile.gettempdir()) / "material-icons.ttf"
font.save(str(tmp_ttf))

png_img = _render_icon(512, tmp_ttf, glyph_char)
png_img.save("C:/Users/guzic/Documents/GitHub/wywiady/extension/icon.png")
png_img.save(f"C:/Users/guzic/Documents/GitHub/wywiady/extension/icon_{BRAND_ICON_TAG}.png")

ico_sizes = [
    (16, 16),
    (20, 20),
    (24, 24),
    (32, 32),
    (40, 40),
    (48, 48),
    (64, 64),
    (96, 96),
    (128, 128),
    (256, 256),
]
png_img.save(
    "C:/Users/guzic/Documents/GitHub/wywiady/extension/icon.ico",
    sizes=ico_sizes,
)
png_img.save(
    f"C:/Users/guzic/Documents/GitHub/wywiady/extension/icon_{BRAND_ICON_TAG}.ico",
    sizes=ico_sizes,
)

# Pre-rendered PNGs for Tk window icons (crisp at each size)
for size in [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]:
    img = _render_icon(size, tmp_ttf, glyph_char)
    img.save(f"C:/Users/guzic/Documents/GitHub/wywiady/extension/icon_{BRAND_ICON_TAG}_{size}.png")

try:
    os.remove(tmp_ttf)
except Exception:
    pass

print("Icon created!")
