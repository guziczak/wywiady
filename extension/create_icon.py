from PIL import Image, ImageDraw

SIZE = 256
BG = (248, 250, 252)          # slate-50
FOLDER = (15, 118, 110)       # teal-700
FOLDER_TAB = (20, 184, 166)   # teal-500
CROSS = (255, 255, 255)       # white

img = Image.new('RGBA', (SIZE, SIZE), BG)
draw = ImageDraw.Draw(img)

# Folder body
pad = int(SIZE * 0.1)
left = pad
right = SIZE - pad
top = int(SIZE * 0.36)
bottom = int(SIZE * 0.86)
radius = int(SIZE * 0.08)
draw.rounded_rectangle([left, top, right, bottom], radius=radius, fill=FOLDER)

# Folder tab
tab_width = int((right - left) * 0.45)
tab_height = int(SIZE * 0.12)
tab_left = left + int(SIZE * 0.03)
tab_top = top - tab_height + int(SIZE * 0.02)
tab_right = tab_left + tab_width
tab_bottom = top + int(SIZE * 0.02)
tab_radius = int(SIZE * 0.06)
draw.rounded_rectangle(
    [tab_left, tab_top, tab_right, tab_bottom],
    radius=tab_radius,
    fill=FOLDER_TAB
)

# Medical cross on folder
cross_thickness = int(SIZE * 0.12)
cross_length = int(SIZE * 0.38)
cx = (left + right) // 2
cy = (top + bottom) // 2 + int(SIZE * 0.02)

v_left = cx - cross_thickness // 2
v_top = cy - cross_length // 2
v_right = v_left + cross_thickness
v_bottom = v_top + cross_length
draw.rectangle([v_left, v_top, v_right, v_bottom], fill=CROSS)

h_left = cx - cross_length // 2
h_top = cy - cross_thickness // 2
h_right = h_left + cross_length
h_bottom = h_top + cross_thickness
draw.rectangle([h_left, h_top, h_right, h_bottom], fill=CROSS)

img.save('C:/Users/guzic/Documents/GitHub/wywiady/extension/icon.png')
img.save('C:/Users/guzic/Documents/GitHub/wywiady/extension/icon.ico',
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Icon created!")
