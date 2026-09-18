"""Generate Pulse app icons with PIL: black rounded square + green pulse line."""
from PIL import Image, ImageDraw

GREEN = (0, 200, 5)
BLACK = (0, 0, 0)


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # black rounded square (full-bleed for maskable safety)
    d.rounded_rectangle([0, 0, size, size], radius=int(size * 0.225), fill=BLACK)
    # pulse / heartbeat polyline
    w = int(size * 0.075)
    pts = [
        (0.16, 0.55), (0.34, 0.55), (0.42, 0.30), (0.52, 0.72),
        (0.60, 0.44), (0.66, 0.55), (0.84, 0.55),
    ]
    xy = [(x * size, y * size) for x, y in pts]
    d.line(xy, fill=GREEN, width=w, joint="curve")
    for x, y in xy:
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=GREEN)
    return img.convert("RGB")


if __name__ == "__main__":
    import os
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
    for name, size in [("icon-180.png", 180), ("icon-192.png", 192), ("icon-512.png", 512)]:
        make_icon(size).save(os.path.join(out, name), "PNG")
        print("wrote", name)
