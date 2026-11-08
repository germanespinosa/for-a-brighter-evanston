"""Build site icons from assets/img/brand-icon.png; requires Pillow.

Keep stable output URLs and the complete source composition and alpha channel.
"""
from pathlib import Path
import base64
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]


def build():
    with Image.open(ROOT / 'assets/img/brand-icon.png') as opened:
        master = opened.convert('RGBA')
    if master.width != master.height or master.width < 512:
        raise ValueError('Use a square master at least 512 pixels wide.')
    master.info.clear()
    sizes = {'assets/img/icon-48.png': 48, 'assets/img/icon-192.png': 192,
             'assets/img/icon-512.png': 512, 'assets/img/apple-touch-icon.png': 180,
             'assets/img/logo-512.png': 512}
    for relative, size in sizes.items():
        master.resize((size, size), Image.Resampling.LANCZOS).save(
            ROOT / relative, format='PNG', optimize=True)
    master.save(ROOT / 'favicon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])
    # Preserve the historical SVG URL with the same artwork, not a traced substitute.
    encoded = base64.b64encode((ROOT / 'assets/img/icon-192.png').read_bytes()).decode('ascii')
    (ROOT / 'favicon.svg').write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192">'
        f'<image width="192" height="192" href="data:image/png;base64,{encoded}"/>'
        '</svg>\n', encoding='utf-8')
    print('Built consistent ICO, SVG and five PNG icon sizes.')


if __name__ == '__main__':
    build()
