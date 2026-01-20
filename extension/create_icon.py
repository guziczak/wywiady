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

from branding import BRAND_ICON, BRAND_ICON_BG

SIZE = 512
BG = tuple(int(BRAND_ICON_BG.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
FG = (255, 255, 255)        # white

FONT_WOFF2 = (
    Path(nicegui.__file__).parent
    / "static"
    / "fonts"
    / "0c19a63c7528cc1a.woff2"
)
LIGATURE_NAME = BRAND_ICON

def _get_ligature_codepoint(font: TTFont, ligature: str) -> int:
    """Zwraca codepoint glypha dla ligatury Material Icons."""
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
        raise RuntimeError(f"Nie znaleziono ligatury: {ligature}")

    if lig_glyph in glyph_to_code:
        return glyph_to_code[lig_glyph]

    if lig_glyph.startswith("uni"):
        return int(lig_glyph[3:], 16)

    raise RuntimeError(f"Brak codepointu dla glypha: {lig_glyph}")

font = TTFont(str(FONT_WOFF2))
codepoint = _get_ligature_codepoint(font, LIGATURE_NAME)
glyph_char = chr(codepoint)

tmp_ttf = Path(tempfile.gettempdir()) / "material-icons.ttf"
font.save(str(tmp_ttf))

img = Image.new("RGBA", (SIZE, SIZE), BG)
draw = ImageDraw.Draw(img)

max_box = int(SIZE * 0.72)
font_size = SIZE
font_obj = None
while font_size > 10:
    try:
        font_obj = ImageFont.truetype(str(tmp_ttf), font_size)
    except Exception:
        font_obj = None
        break
    bbox = draw.textbbox((0, 0), glyph_char, font=font_obj)
    glyph_w = bbox[2] - bbox[0]
    glyph_h = bbox[3] - bbox[1]
    if glyph_w <= max_box and glyph_h <= max_box:
        break
    font_size -= 8

if font_obj is None:
    raise RuntimeError("Nie udało się załadować fontu Material Icons.")

bbox = draw.textbbox((0, 0), glyph_char, font=font_obj)
glyph_w = bbox[2] - bbox[0]
glyph_h = bbox[3] - bbox[1]
x = (SIZE - glyph_w) // 2 - bbox[0]
y = (SIZE - glyph_h) // 2 - bbox[1]
draw.text((x, y), glyph_char, font=font_obj, fill=FG)

try:
    os.remove(tmp_ttf)
except Exception:
    pass

img.save("C:/Users/guzic/Documents/GitHub/wywiady/extension/icon.png")
img.save(
    "C:/Users/guzic/Documents/GitHub/wywiady/extension/icon.ico",
    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print("Icon created!")
