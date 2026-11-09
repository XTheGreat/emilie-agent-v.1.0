"""Emilie colour palette: sakura rose + bright pink. Made for dark terminals (still readable on light ones)."""
ROSE = "#d9689a"
LAV = "#ffb8e0"                # labels/headings: a brighter pink than ROSE (was lavender)
MUTED = "#8a8a8a"
OK = "#3fa66b"
WARN = "#d99a2b"
ERR = "#d9534f"
ADD = "#3fa66b"
DEL = "#d9534f"


# --- flowing gradient (left -> right) for rules/borders ---
# pink blossom / candy + white + a bright pink accent (the accent stop is only ~1/8 of the cycle)
PALETTE = [(244, 143, 177),   # pink blossom
           (255, 105, 170),   # candy pink
           (255, 176, 208),   # candy lembut
           (255, 234, 243),   # reddish white
           (255, 176, 208),
           (255, 105, 170),
           (244, 143, 177),
           (255, 190, 225)]   # bright pink accent


def gradient_rgb(pos: float) -> tuple[int, int, int]:
    """cyclic pos [0,1) -> colour, smooth interpolation through PALETTE."""
    f = (pos % 1.0) * len(PALETTE)
    i = int(f)
    a, b, k = PALETTE[i % len(PALETTE)], PALETTE[(i + 1) % len(PALETTE)], f - i
    return tuple(int(a[j] + (b[j] - a[j]) * k) for j in range(3))  # type: ignore


def gradient_hex(pos: float) -> str:
    r, g, b = gradient_rgb(pos)
    return f"#{r:02x}{g:02x}{b:02x}"


def flow_hex(x: float, t: float, scale: float = 0.008, speed: float = 0.06) -> str:
    """Colour at column x at time t; the pattern slowly shifts to the RIGHT (~17 s per cycle)."""
    return gradient_hex(x * scale - t * speed)
