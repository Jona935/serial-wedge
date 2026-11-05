"""Genera el icono: código de barras con línea láser roja sobre un cuadrado azul oscuro.

Uso: python tools/make_icon.py  (escribe assets/serial-wedge.png, .ico y la copia del paquete)
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
BG, BAR, LASER = (22, 45, 94, 255), (245, 247, 250, 255), (235, 40, 40, 255)
# anchos de barras y espacios (en unidades) de izquierda a derecha
PATTERN = [2, 1, 1, 1, 3, 1, 1, 2, 2, 1, 1, 1, 3, 2, 1, 1, 2, 1, 1, 1, 2]


def draw(size: int = 256) -> Image.Image:
    s = size / 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(48 * s), fill=BG)
    left, right, top, bottom = 40 * s, 216 * s, 58 * s, 198 * s
    unit = (right - left) / sum(PATTERN)
    x = left
    for i, w in enumerate(PATTERN):
        if i % 2 == 0:  # barra; los impares son espacios
            d.rectangle([round(x), round(top), round(x + w * unit) - 1, round(bottom)], fill=BAR)
        x += w * unit
    mid, half = 128 * s, max(1, round(5 * s))
    d.rectangle([round(20 * s), round(mid - half), round(236 * s), round(mid + half)], fill=LASER)
    return img


def main():
    img = draw(256)
    (ROOT / "assets").mkdir(exist_ok=True)
    pkg = ROOT / "src" / "serial_wedge" / "assets"
    pkg.mkdir(parents=True, exist_ok=True)
    img.save(ROOT / "assets" / "serial-wedge.png")
    img.save(pkg / "serial-wedge.png")
    img.save(ROOT / "assets" / "serial-wedge.ico",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Iconos generados en", ROOT / "assets")


if __name__ == "__main__":
    main()
