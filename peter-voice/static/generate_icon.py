"""Generate a simple PWA icon for Peter Voice."""
from PIL import Image, ImageDraw, ImageFont

size = 192
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Discord blurple circle
draw.ellipse([8, 8, size - 8, size - 8], fill="#5865F2")

# White "P"
try:
    font = ImageFont.truetype("arial.ttf", size=120)
except Exception:
    font = ImageFont.load_default()
bbox = draw.textbbox((0, 0), "P", font=font)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
draw.text(((size - tw) / 2, (size - th) / 2 - 8), "P", fill="white", font=font)

img.save("icon-192.png")
print("Generated icon-192.png")
