from PIL import Image, ImageDraw

SIZE = 256
BG = (15, 118, 110)          # teal-700
FG = (248, 250, 252)         # slate-50
ACCENT = (56, 189, 248)      # sky-400

img = Image.new('RGBA', (SIZE, SIZE), BG)
draw = ImageDraw.Draw(img)

# Medical cross
cross_thickness = int(SIZE * 0.18)
cross_length = int(SIZE * 0.62)
cx = cy = SIZE // 2

v_left = cx - cross_thickness // 2
v_top = cy - cross_length // 2
v_right = v_left + cross_thickness
v_bottom = v_top + cross_length
draw.rectangle([v_left, v_top, v_right, v_bottom], fill=FG)

h_left = cx - cross_length // 2
h_top = cy - cross_thickness // 2
h_right = h_left + cross_length
h_bottom = h_top + cross_thickness
draw.rectangle([h_left, h_top, h_right, h_bottom], fill=FG)

# Stethoscope accent
circle_r = int(SIZE * 0.09)
circle_cx = int(SIZE * 0.74)
circle_cy = int(SIZE * 0.74)
draw.ellipse(
    [circle_cx - circle_r, circle_cy - circle_r, circle_cx + circle_r, circle_cy + circle_r],
    outline=ACCENT,
    width=max(2, SIZE // 32)
)
line_w = max(2, SIZE // 32)
draw.line(
    [(cx + cross_thickness // 2, cy + cross_thickness // 2 + 8),
     (circle_cx - circle_r, circle_cy - circle_r)],
    fill=ACCENT,
    width=line_w
)

img.save('C:/Users/guzic/Documents/GitHub/wywiady/extension/icon.png')
img.save('C:/Users/guzic/Documents/GitHub/wywiady/extension/icon.ico',
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Icon created!")
