"""Build data/cards.json: the 22 majors, with the keyword line already written
for each card in the main app's tarot.csv carried along.

The app does not display those keywords — only the card name and its
orientation — but they are kept in the data in case they are wanted later.

    ./venv/bin/python tools/build_card_data.py
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT.parent / "The Tarot App" / "tarot.csv"
OUT = ROOT / "data" / "cards.json"

# CSV rows are in Marseille order: Le Bateleur (I) .. Le Monde (XXI), then Le Fou.
ORDER = [
    ("01", "I", "Le Bateleur"),
    ("02", "II", "La Papesse"),
    ("03", "III", "L'Impératrice"),
    ("04", "IIII", "L'Empereur"),
    ("05", "V", "Le Pape"),
    ("06", "VI", "L'Amoureux"),
    ("07", "VII", "Le Chariot"),
    ("08", "VIII", "La Justice"),
    ("09", "IX", "L'Hermite"),
    ("10", "X", "La Roue de la Fortune"),
    ("11", "XI", "La Force"),
    ("12", "XII", "Le Pendu"),
    ("13", "XIII", "La Mort"),
    ("14", "XIIII", "La Tempérance"),
    ("15", "XV", "Le Diable"),
    ("16", "XVI", "La Maison Dieu"),
    ("17", "XVII", "L'Étoile"),
    ("18", "XVIII", "La Lune"),
    ("19", "XIX", "Le Soleil"),
    ("20", "XX", "Le Jugement"),
    ("21", "XXI", "Le Monde"),
    ("00", "", "Le Fou"),
]


def keywords(cell):
    """The first line of each meaning is the keyword summary."""
    line = (cell or "").strip().split("\n")[0].strip()
    line = line.lstrip("-").strip()
    return " ".join(line.split())


def main():
    hints = {}
    if CSV.exists():
        with CSV.open(encoding="utf-8") as fh:
            # The header row has an empty first cell, so this also skips it.
            rows = [r for r in csv.reader(fh) if r and r[0].strip()]
        if len(rows) != len(ORDER):
            raise SystemExit(f"expected {len(ORDER)} card rows in tarot.csv, found {len(rows)}")
        for (number, _, _), row in zip(ORDER, rows):
            hints[number] = {
                "upright": keywords(row[1] if len(row) > 1 else ""),
                "reversed": keywords(row[2] if len(row) > 2 else ""),
            }
    else:
        print(f"warning: {CSV} not found, cards will have no keyword hints")

    cards = [
        {
            "id": number,
            "numeral": numeral,
            "name": name,
            "hint_upright": hints.get(number, {}).get("upright", ""),
            "hint_reversed": hints.get(number, {}).get("reversed", ""),
        }
        for number, numeral, name in sorted(ORDER)
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(cards)} cards to {OUT}")


if __name__ == "__main__":
    main()
