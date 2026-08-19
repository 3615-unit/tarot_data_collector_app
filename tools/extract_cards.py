"""Cut the major arcana out of the printable mini-tarot PDF.

The PDF is a single page holding a grid of vector cards. It is rendered at high
resolution through Quartz, the card frames are located by their border lines,
and each major arcanum is written to static/cards/<number>.png.

Three majors are absent from that sheet (La Force, La Mort, L'Étoile); they are
drawn separately by tools/generate_cards.py in a matching style.

    ./venv/bin/python tools/extract_cards.py [path/to/sheet.pdf]
"""

import sys
from pathlib import Path

import numpy as np
import Quartz
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "static" / "cards"
DEFAULT_PDF = Path.home() / "Desktop" / "mini-tarot-cards-printable.pdf"

SCALE = 8          # render the page at 8x its 750x1125pt size
OUT_WIDTH = 700    # final card width in pixels
MARGIN = 10        # white kept around each card's outer border

# Where each major sits on the sheet, as (row, column), 1-indexed.
LAYOUT = {
    "00": (1, 3),  # The Fool
    "01": (2, 1),  # The Magician
    "02": (1, 6),  # The High Priestess
    "03": (2, 2),  # The Empress
    "04": (3, 4),  # The Emperor
    "05": (3, 5),  # The Hierophant
    "06": (1, 1),  # The Lovers
    "07": (4, 1),  # The Chariot
    "08": (2, 3),  # Justice
    "09": (1, 5),  # The Hermit
    "10": (2, 5),  # The Wheel
    "12": (2, 6),  # The Hanged Man
    "14": (4, 2),  # Temperance
    "15": (4, 5),  # The Devil
    "16": (3, 1),  # The Tower
    "18": (1, 4),  # The Moon
    "19": (1, 2),  # The Sun
    "20": (3, 2),  # Judgement
    "21": (5, 1),  # The World
}


def render_pdf(pdf_path, scale):
    raw = str(pdf_path).encode()
    url = Quartz.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), False)
    doc = Quartz.CGPDFDocumentCreateWithURL(url)
    if doc is None:
        raise SystemExit(f"could not open {pdf_path}")
    page = Quartz.CGPDFDocumentGetPage(doc, 1)
    rect = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFMediaBox)
    width = int(rect.size.width * scale)
    height = int(rect.size.height * scale)

    space = Quartz.CGColorSpaceCreateDeviceRGB()
    ctx = Quartz.CGBitmapContextCreate(
        None, width, height, 8, width * 4, space, Quartz.kCGImageAlphaNoneSkipLast
    )
    Quartz.CGContextSetRGBFillColor(ctx, 1, 1, 1, 1)
    Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, width, height))
    Quartz.CGContextScaleCTM(ctx, scale, scale)
    Quartz.CGContextSetInterpolationQuality(ctx, Quartz.kCGInterpolationHigh)
    Quartz.CGContextDrawPDFPage(ctx, page)

    image = Quartz.CGBitmapContextCreateImage(ctx)
    data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(image))
    pixels = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 4)[:, :, :3]
    return Image.fromarray(pixels)


def runs(flags, min_length):
    out, start = [], None
    for i, on in enumerate(flags):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= min_length:
                out.append((start, i - 1))
            start = None
    if start is not None and len(flags) - start >= min_length:
        out.append((start, len(flags) - 1))
    return out


def find_grid(dark):
    """Locate the card frames: rows from a left border, columns from a top border."""
    height, width = dark.shape
    thickness = max(3, width // 700)

    # A card's left border is the first long vertical line on the page.
    column_runs = [
        max(runs(dark[:, x], height // 12), key=lambda r: r[1] - r[0], default=None)
        for x in range(width // 10)
    ]
    first_x = next(x for x, r in enumerate(column_runs) if r and r[1] - r[0] > height // 8)

    rows = runs(dark[:, first_x:first_x + thickness].any(axis=1), height // 12)
    if not rows:
        raise SystemExit("no card rows found")

    # Read the columns off the top border of the first row.
    top = rows[0][0]
    band = dark[top:top + thickness * 2, :].any(axis=0)
    columns = runs(band, width // 12)
    return rows, columns


def main():
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf_path.exists():
        raise SystemExit(f"{pdf_path} not found")

    page = render_pdf(pdf_path, SCALE)
    dark = np.asarray(page.convert("L")) < 128
    rows, columns = find_grid(dark)
    print(f"grid: {len(rows)} rows x {len(columns)} columns")

    DEST.mkdir(parents=True, exist_ok=True)
    for number, (row, column) in sorted(LAYOUT.items()):
        if row > len(rows) or column > len(columns):
            raise SystemExit(f"card {number} at row {row} col {column} is outside the grid")
        top, bottom = rows[row - 1]
        left, right = columns[column - 1]
        card = page.crop(
            (
                max(0, left - MARGIN),
                max(0, top - MARGIN),
                min(page.width, right + 1 + MARGIN),
                min(page.height, bottom + 1 + MARGIN),
            )
        )
        card = card.resize(
            (OUT_WIDTH, round(card.height * OUT_WIDTH / card.width)), Image.LANCZOS
        )
        out = DEST / f"{number}.png"
        card.convert("L").save(out, "PNG", optimize=True)
        print(f"{number}  row {row} col {column} -> {out.name}  {card.width}x{card.height}")


if __name__ == "__main__":
    main()
