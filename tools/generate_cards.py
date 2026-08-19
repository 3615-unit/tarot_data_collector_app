"""Draw the three majors that are missing from the printable sheet.

La Force, La Mort and L'Étoile are not on mini-tarot-cards-printable.pdf, so
they are drawn here in the same style as the extracted cards: white card, heavy
black frame, roman numeral on top, bold title underneath, black line art and a
scatter of four-pointed sparkles. Numbering follows the sheet's deck (Justice
XI, Strength VIII), not the Marseille order.

    ./venv/bin/python tools/generate_cards.py
"""

import math
import random
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / "static" / "cards"

W, H = 700, 1268
FRAME = (8.5, 24.5, 683, 1116)  # x, y, width, height of the heavy outer frame
ART_X, ART_Y = 350, 620         # origin of the art group

INK = "#1a1a1a"
STROKE = 7


def sparkle(x, y, s=1.0):
    """The little four-pointed stars scattered across every card in the deck."""
    return (
        f'<path transform="translate({x},{y}) scale({s})" fill="{INK}" stroke="none" '
        f'd="M0 -20 Q3 -3 20 0 Q3 3 0 20 Q-3 3 -20 0 Q-3 -3 0 -20 Z"/>'
    )


def sparkles(seed, count=13, avoid=()):
    """Scatter sparkles over the art field, skipping circles listed in `avoid`."""
    rng = random.Random(seed)
    out = []
    placed = []
    while len(out) < count:
        x = rng.uniform(-250, 250)
        y = rng.uniform(-400, 400)
        if any(math.hypot(x - cx, y - cy) < r for cx, cy, r in avoid):
            continue
        if any(math.hypot(x - px, y - py) < 90 for px, py in placed):
            continue
        placed.append((x, y))
        out.append(sparkle(round(x), round(y), rng.uniform(0.7, 1.15)))
    return "".join(out)


def star(cx, cy, points, outer, inner, fill="none", width=STROKE):
    coords = []
    for i in range(points * 2):
        r = outer if i % 2 == 0 else inner
        a = -math.pi / 2 + i * math.pi / points
        coords.append(f"{cx + r * math.cos(a):.1f} {cy + r * math.sin(a):.1f}")
    return (
        f'<path d="M{" L".join(coords)} Z" fill="{fill}" stroke="{INK}" '
        f'stroke-width="{width}" stroke-linejoin="round"/>'
    )


def water(y0, count=4, half=250, gap=34):
    lines = []
    for i in range(count):
        w = half - i * 18
        lines.append(f"M{-w} {y0 + i * gap} H{w}")
    return f'<path d="{" ".join(lines)}" fill="none" stroke="{INK}" stroke-width="{STROKE}"/>'


# --------------------------------------------------------------------- scenes

STRENGTH = f"""
  <path d="M-60 -352 C-60 -392 -20 -392 0 -352 C20 -312 60 -312 60 -352
           C60 -392 20 -392 0 -352 C-20 -312 -60 -312 -60 -352 Z"
        fill="none" stroke="{INK}" stroke-width="{STROKE}"/>
  {star(0, -20, 13, 244, 190, "#ffffff")}
  <circle cx="0" cy="-20" r="172" fill="#ffffff" stroke="{INK}" stroke-width="{STROKE}"/>
  <path d="M-138 -122 L-146 -228 L-56 -172" fill="#ffffff" stroke="{INK}" stroke-width="{STROKE}" stroke-linejoin="round"/>
  <path d="M138 -122 L146 -228 L56 -172" fill="#ffffff" stroke="{INK}" stroke-width="{STROKE}" stroke-linejoin="round"/>
  <circle cx="-62" cy="-62" r="19" fill="{INK}"/>
  <circle cx="62" cy="-62" r="19" fill="{INK}"/>
  <path d="M-34 12 L0 44 L34 12 Z" fill="{INK}"/>
  <path d="M-62 74 Q0 118 62 74" fill="none" stroke="{INK}" stroke-width="{STROKE}"/>
  <path d="M0 44 V74" fill="none" stroke="{INK}" stroke-width="{STROKE}"/>
  <path d="M-88 52 H-166 M-90 84 H-160 M88 52 H166 M90 84 H160"
        fill="none" stroke="{INK}" stroke-width="5"/>
  {water(300, 3)}
"""

DEATH = f"""
  <path d="M236 392 L286 -352" fill="none" stroke="{INK}" stroke-width="{STROKE}"/>
  <path d="M286 -352 Q150 -392 76 -286" fill="none" stroke="{INK}" stroke-width="{STROKE}"/>
  <path d="M272 -288 Q176 -318 124 -244" fill="none" stroke="{INK}" stroke-width="5"/>
  <path d="M-224 -60 Q-224 -270 -54 -270 Q116 -270 116 -60 Q116 30 60 60
           L60 148 Q-54 190 -168 148 L-168 60 Q-224 30 -224 -60 Z"
        fill="#ffffff" stroke="{INK}" stroke-width="{STROKE}" stroke-linejoin="round"/>
  <circle cx="-142" cy="-96" r="44" fill="{INK}"/>
  <circle cx="34" cy="-96" r="44" fill="{INK}"/>
  <path d="M-70 -6 L-54 34 L-38 -6 Z" fill="{INK}"/>
  <path d="M-168 84 H60 M-130 84 V148 M-92 84 V156 M-54 84 V160 M-16 84 V156 M22 84 V148"
        fill="none" stroke="{INK}" stroke-width="5"/>
  {water(300, 3)}
"""

THE_STAR = f"""
  {star(0, -250, 8, 158, 58, INK)}
  {star(-196, -344, 4, 44, 14, INK)}
  {star(196, -344, 4, 44, 14, INK)}
  {star(-248, -178, 4, 38, 12, INK)}
  {star(248, -178, 4, 38, 12, INK)}
  {star(-150, -62, 4, 34, 11, INK)}
  {star(150, -62, 4, 34, 11, INK)}
  {star(0, -404, 4, 34, 11, INK)}
  <path d="M-238 40 H-118 L-138 148 H-218 Z" fill="#ffffff" stroke="{INK}"
        stroke-width="{STROKE}" stroke-linejoin="round"/>
  <path d="M118 40 H238 L218 148 H138 Z" fill="#ffffff" stroke="{INK}"
        stroke-width="{STROKE}" stroke-linejoin="round"/>
  <path d="M-146 152 Q-132 214 -150 268" fill="none" stroke="{INK}" stroke-width="{STROKE}"/>
  <path d="M146 152 Q132 214 150 268" fill="none" stroke="{INK}" stroke-width="{STROKE}"/>
  {water(292, 4)}
"""

CARDS = [
    ("11", "VIII", "STRENGTH", STRENGTH, ((0, -20, 260),)),
    ("13", "XIII", "DEATH", DEATH, ((-54, -60, 250), (200, -100, 140))),
    ("17", "XVII", "THE STAR", THE_STAR, ((0, -250, 200),)),
]

FONT = "'Helvetica Neue', Helvetica, Arial, sans-serif"


def title_size(title):
    return 78 if len(title) <= 8 else 62


def render(numeral, title, scene, avoid, seed):
    x, y, w, h = FRAME
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="{title}">
  <rect width="{W}" height="{H}" fill="#ffffff"/>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{INK}" stroke-width="11"/>
  <text x="{W / 2}" y="118" text-anchor="middle" font-family="{FONT}" font-weight="700"
        font-size="58" letter-spacing="7" fill="{INK}">{numeral}</text>
  <g transform="translate({ART_X},{ART_Y})">{sparkles(seed, avoid=avoid)}{scene}</g>
  <text x="{W / 2}" y="1230" text-anchor="middle" font-family="{FONT}" font-weight="700"
        font-size="{title_size(title)}" letter-spacing="7" fill="{INK}">{title}</text>
</svg>
"""


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    for seed, (number, numeral, title, scene, avoid) in enumerate(CARDS):
        (DEST / f"{number}.svg").write_text(
            render(numeral, title, scene, avoid, seed + 7), encoding="utf-8"
        )
        print(f"{number}  {title}")
    print(f"Wrote {len(CARDS)} cards to {DEST}")


if __name__ == "__main__":
    main()
