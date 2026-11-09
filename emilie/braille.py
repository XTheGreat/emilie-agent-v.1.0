"""Convert an image into colored braille dot art (a rich Text)."""
from PIL import Image, ImageOps
from rich.text import Text

# braille dot bit for (x, y) inside a 2x4 cell
_BITS = {(0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (1, 0): 0x08,
         (1, 1): 0x10, (1, 2): 0x20, (0, 3): 0x40, (1, 3): 0x80}


def image_to_braille(path: str, width: int = 34, threshold: int = 225,
                     color: bool = True, dither: bool = True) -> Text:
    """width = number of terminal columns. Pixels lighter than `threshold`
    (or transparent) are left blank, so a white/transparent background vanishes."""
    img = Image.open(path).convert("RGBA")
    w_px = width * 2
    h_px = max(4, round(w_px * img.height / img.width))
    h_px += (-h_px) % 4
    img = img.resize((w_px, h_px), Image.LANCZOS)
    px = img.load()
    # Floyd-Steinberg dither: a lit dot = a dark part (ink)
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=2)
    dith = gray.convert("1").load() if dither else None

    out = Text()
    for cy in range(0, h_px, 4):
        for cx in range(0, w_px, 2):
            bits, rs, gs, bs, n = 0, 0, 0, 0, 0
            for (dx, dy), bit in _BITS.items():
                r, g, b, a = px[cx + dx, cy + dy]
                lum = 0.299 * r + 0.587 * g + 0.114 * b
                on = (dith[cx + dx, cy + dy] == 0) if dither else lum < threshold
                if a > 128 and on:
                    bits |= bit
                    rs += r; gs += g; bs += b; n += 1
            ch = chr(0x2800 + bits)
            if n and color:
                out.append(ch, style=f"#{rs // n:02x}{gs // n:02x}{bs // n:02x}")
            else:
                out.append(ch)
        out.append("\n")
    out.rstrip()
    return out
