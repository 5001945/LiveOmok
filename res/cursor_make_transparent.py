from PIL import Image

img = Image.open("cursor_0_binary.png")
img = img.convert("RGBA")
data = img.getdata()

newdata = []
for item in data:
    if item[:3] == (255, 255, 255):
        newdata.append((255, 255, 255, 0))
    else:
        newdata.append(item)

img.putdata(newdata)
img.save("cursor_0_black_transparent.png", "PNG")
