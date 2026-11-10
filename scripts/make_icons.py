# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow==11.3.0"]
# ///
"""Draw the MediaHarvest logo and write every icon the UI ships.

Run from the repo root (in the dev container):  uv run scripts/make_icons.py

The logo: a down arrow dropping into a tray, white on a green-to-teal
rounded square. The SVGs are written as text; the PNGs and .ico are drawn
at 4x and scaled down for smooth edges.
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / 'ui' / 'src' / 'assets' / 'icons'
TOP, BOTTOM = (34, 197, 94), (15, 118, 110)  # green-500 -> teal-700

# Shapes in a 0..1 box, shared by the PNG and SVG versions.
SHAFT = (0.43, 0.18, 0.57, 0.50)              # x0, y0, x1, y1
HEAD = [(0.28, 0.46), (0.72, 0.46), (0.50, 0.68)]
TRAY = [(0.22, 0.60), (0.22, 0.80), (0.78, 0.80), (0.78, 0.60)]
TRAY_W = 0.075
RADIUS = 0.22


def draw(size: int) -> Image.Image:
    s = size * 4
    grad = Image.new('RGB', (1, s))
    for y in range(s):
        t = y / (s - 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    grad = grad.resize((s, s))
    mask = Image.new('L', (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=RADIUS * s, fill=255)
    img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    x0, y0, x1, y1 = SHAFT
    d.rounded_rectangle((x0 * s, y0 * s, x1 * s, y1 * s), radius=0.03 * s, fill=white)
    d.polygon([(x * s, y * s) for x, y in HEAD], fill=white)
    d.line([(x * s, y * s) for x, y in TRAY], fill=white, width=round(TRAY_W * s), joint='curve')
    r = TRAY_W * s / 2  # round the two open ends of the tray
    for x, y in (TRAY[0], TRAY[-1]):
        d.ellipse((x * s - r, y * s - r, x * s + r, y * s + r), fill=white)
    return img.resize((size, size), Image.LANCZOS)


def svg(mono: bool = False) -> str:
    x0, y0, x1, y1 = (v * 100 for v in SHAFT)
    head = ' '.join(f'{x * 100:g},{y * 100:g}' for x, y in HEAD)
    tray = ' '.join(f'{x * 100:g},{y * 100:g}' for x, y in TRAY)
    fg = '#000' if mono else '#fff'
    marks = (
        f'<rect x="{x0:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" rx="3" fill="{fg}"/>'
        f'<polygon points="{head}" fill="{fg}"/>'
        f'<polyline points="{tray}" fill="none" stroke="{fg}" stroke-width="{TRAY_W * 100:g}" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    )
    if mono:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">{marks}</svg>\n'
    top = '#%02x%02x%02x' % TOP
    bottom = '#%02x%02x%02x' % BOTTOM
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/>'
        '</linearGradient></defs>'
        f'<rect width="100" height="100" rx="{RADIUS * 100:g}" fill="url(#g)"/>{marks}</svg>\n'
    )


def main() -> None:
    ICONS.mkdir(parents=True, exist_ok=True)
    pngs = {
        'favicon-16x16.png': 16,
        'favicon-32x32.png': 32,
        'apple-touch-icon.png': 180,
        'mstile-150x150.png': 150,
        'android-chrome-192x192.png': 192,
        'android-chrome-384x384.png': 384,
        'android-chrome-512x512.png': 512,
    }
    for name, size in pngs.items():
        draw(size).save(ICONS / name, optimize=True)
    big = draw(256)
    for ico in (ICONS / 'favicon.ico', ROOT / 'ui' / 'src' / 'favicon.ico'):
        big.save(ico, sizes=[(16, 16), (32, 32), (48, 48)])
    (ICONS / 'logo.svg').write_text(svg())
    (ICONS / 'safari-pinned-tab.svg').write_text(svg(mono=True))
    draw(1024).save(ROOT / 'docs' / 'logo.png', optimize=True) if (ROOT / 'docs').is_dir() else None
    print('icons written to', ICONS)


if __name__ == '__main__':
    main()
