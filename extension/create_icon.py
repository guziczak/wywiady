from PIL import Image, ImageDraw
img = Image.new('RGB', (128, 128), color=(99, 102, 241))
draw = ImageDraw.Draw(img)
draw.text((30, 35), "W+", fill='white')
img.save('C:/Users/guzic/Documents/GitHub/wywiady/extension/icon.png')
print("Icon created!")
