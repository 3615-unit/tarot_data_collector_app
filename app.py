"""Combinaisons — data collection for pairs of major arcana.

231 pairs x 4 orientations = 924 combinations. One combination is shown at a
time with four fields (Amour, Argent, Projet/Travail, Famille/Entourage) that
autosave as they are typed.

Storage is SQLite locally, Postgres when DATABASE_URL is set.
"""

import csv
import io
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from random import Random

from flask import (
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

ROOT = Path(__file__).resolve().parent

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

ACCESS_CODE = os.environ.get("ACCESS_CODE", "").strip()
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SQLITE_PATH = os.environ.get("SQLITE_PATH", str(ROOT / "combinaisons.db"))

FIELDS = ("amour", "argent", "projet", "famille")
ORIENTATIONS = ("U", "R")
# Series are served in this order so that a complete upright set exists first.
PHASES = [
    ("U", "U", "Les deux cartes à l'endroit"),
    ("U", "R", "La deuxième carte renversée"),
    ("R", "U", "La première carte renversée"),
    ("R", "R", "Les deux cartes renversées"),
]

CARDS = json.loads((ROOT / "data" / "cards.json").read_text(encoding="utf-8"))
CARDS_BY_ID = {card["id"]: card for card in CARDS}
CARD_IDS = [card["id"] for card in CARDS]


def card_image(card_id):
    """Most cards are PNGs cut from the printable sheet; three are drawn as SVG."""
    for extension in ("png", "svg", "jpg", "webp"):
        if (ROOT / "static" / "cards" / f"{card_id}.{extension}").exists():
            return f"cards/{card_id}.{extension}"
    raise SystemExit(f"no image found for card {card_id}")


CARD_IMAGES = {card_id: card_image(card_id) for card_id in CARD_IDS}


# Fixed forever. A position is what the resume pointer, the #index in the URL
# and any shared link all refer to, so re-rolling this seed would drop her on a
# different card and break every saved link. Stored rows are keyed by combo_key,
# never by position, so the order can change without touching existing data —
# but there is no reason to, and every reason not to.
SHUFFLE_SEED = 20260818


def build_combos():
    """All (card, orientation) pairs, grouped by series and shuffled inside each.

    The series stay in order so a complete upright set exists first, but within
    a series the pairs are jumbled: unshuffled, the first 21 combinations all
    start with Le Fou, the next 20 with Le Bateleur, and answering them in that
    order turns into pattern-matching rather than reading.
    """
    combos = []
    for phase_index, (orient_a, orient_b, label) in enumerate(PHASES):
        serie = []
        for i, card_a in enumerate(CARD_IDS):
            for card_b in CARD_IDS[i + 1:]:
                serie.append(
                    {
                        "key": f"{card_a}{orient_a}-{card_b}{orient_b}",
                        "card_a": card_a,
                        "orient_a": orient_a,
                        "card_b": card_b,
                        "orient_b": orient_b,
                        "phase": phase_index,
                        "phase_label": label,
                    }
                )
        Random(SHUFFLE_SEED + phase_index).shuffle(serie)
        combos.extend(serie)
    return combos


COMBOS = build_combos()
COMBO_INDEX = {combo["key"]: i for i, combo in enumerate(COMBOS)}
TOTAL = len(COMBOS)


# --------------------------------------------------------------------- storage

def using_postgres():
    return bool(DATABASE_URL)


def connect():
    if using_postgres():
        import psycopg2

        url = DATABASE_URL
        if url.startswith("postgres://"):  # some hosts still hand out the old scheme
            url = url.replace("postgres://", "postgresql://", 1)
        # Fail fast on a bad host/URL. Without this psycopg2 has no timeout, so a
        # mistyped DATABASE_URL hangs the import-time init_db() until gunicorn's
        # worker times out — which Render reports only as "service won't start",
        # with no cause. A short timeout turns that into a clear error in the log.
        return psycopg2.connect(url, connect_timeout=10)

    import sqlite3

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db():
    """A connection per request, committed on success and always closed.

    `with connection` only wraps a transaction in both drivers, so the close
    has to be explicit or a hosted Postgres runs out of connections.
    """
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def q(sql):
    """SQLite uses ? placeholders, psycopg2 uses %s."""
    return sql if using_postgres() else sql.replace("%s", "?")


def init_db():
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                combo_key  TEXT PRIMARY KEY,
                card_a     TEXT NOT NULL,
                orient_a   TEXT NOT NULL,
                card_b     TEXT NOT NULL,
                orient_b   TEXT NOT NULL,
                amour      TEXT NOT NULL DEFAULT '',
                argent     TEXT NOT NULL DEFAULT '',
                projet     TEXT NOT NULL DEFAULT '',
                famille    TEXT NOT NULL DEFAULT '',
                updated_at TEXT
            )
            """
        )


def fetch_entry(combo_key):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            q("SELECT amour, argent, projet, famille FROM entries WHERE combo_key = %s"),
            (combo_key,),
        )
        row = cur.fetchone()
    if not row:
        return {field: "" for field in FIELDS}
    return dict(zip(FIELDS, (value or "" for value in row)))


def save_entry(combo, values):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            q(
                """
                INSERT INTO entries
                    (combo_key, card_a, orient_a, card_b, orient_b,
                     amour, argent, projet, famille, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (combo_key) DO UPDATE SET
                    amour = EXCLUDED.amour,
                    argent = EXCLUDED.argent,
                    projet = EXCLUDED.projet,
                    famille = EXCLUDED.famille,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            (
                combo["key"],
                combo["card_a"],
                combo["orient_a"],
                combo["card_b"],
                combo["orient_b"],
                values["amour"],
                values["argent"],
                values["projet"],
                values["famille"],
                now,
            ),
        )


def filled_keys():
    """Keys that have at least one non-empty field."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT combo_key,
                   CASE WHEN amour <> '' AND argent <> '' AND projet <> '' AND famille <> ''
                        THEN 1 ELSE 0 END AS complete
            FROM entries
            WHERE amour <> '' OR argent <> '' OR projet <> '' OR famille <> ''
            """
        )
        return {row[0]: bool(row[1]) for row in cur.fetchall()}


def all_entries():
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT combo_key, card_a, orient_a, card_b, orient_b,
                   amour, argent, projet, famille, updated_at
            FROM entries ORDER BY combo_key
            """
        )
        columns = [
            "combo_key", "card_a", "orient_a", "card_b", "orient_b",
            "amour", "argent", "projet", "famille", "updated_at",
        ]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


# ------------------------------------------------------------------------ auth

def protected(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if ACCESS_CODE and not session.get("ok"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if not ACCESS_CODE:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        if request.form.get("code", "").strip() == ACCESS_CODE:
            session["ok"] = True
            session.permanent = True
            return redirect(url_for("index"))
        error = "Code incorrect"
    return render_template("login.html", error=error)


# ------------------------------------------------------------------------ views

def describe(combo, values=None, progress=None):
    def side(card_id, orientation):
        card = CARDS_BY_ID[card_id]
        return {
            "id": card_id,
            "name": card["name"],
            "numeral": card["numeral"],
            "orientation": orientation,
            "reversed": orientation == "R",
            "hint": card["hint_reversed"] if orientation == "R" else card["hint_upright"],
            "image": url_for("static", filename=CARD_IMAGES[card_id]),
        }

    payload = {
        "index": COMBO_INDEX[combo["key"]],
        "total": TOTAL,
        "key": combo["key"],
        "phase": combo["phase"],
        "phase_label": combo["phase_label"],
        "a": side(combo["card_a"], combo["orient_a"]),
        "b": side(combo["card_b"], combo["orient_b"]),
    }
    if values is not None:
        payload["values"] = values
    if progress is not None:
        payload["progress"] = progress
    return payload


def progress_summary(known=None):
    known = filled_keys() if known is None else known
    started = len(known)
    complete = sum(1 for is_complete in known.values() if is_complete)
    return {"total": TOTAL, "started": started, "complete": complete}


@app.route("/")
@protected
def index():
    return render_template("index.html", total=TOTAL, fields=FIELDS)


@app.route("/api/combo/<int:index>")
@protected
def get_combo(index):
    if not 0 <= index < TOTAL:
        return jsonify({"error": "index hors limites"}), 404
    combo = COMBOS[index]
    return jsonify(describe(combo, fetch_entry(combo["key"]), progress_summary()))


@app.route("/api/combo/<int:index>", methods=["POST"])
@protected
def post_combo(index):
    if not 0 <= index < TOTAL:
        return jsonify({"error": "index hors limites"}), 404
    body = request.get_json(silent=True) or {}
    values = {field: (body.get(field) or "").strip() for field in FIELDS}
    combo = COMBOS[index]
    save_entry(combo, values)
    return jsonify({"saved": True, "key": combo["key"], "progress": progress_summary()})


@app.route("/api/next-empty")
@protected
def next_empty():
    """First combination after `from` that still needs work.

    All four fields are required, so a half-filled combination counts as
    unfinished here, not just an untouched one.
    """
    start = request.args.get("from", type=int, default=-1)
    known = filled_keys()
    order = list(range(start + 1, TOTAL)) + list(range(0, max(start + 1, 0)))
    for i in order:
        if not known.get(COMBOS[i]["key"], False):
            return jsonify({"index": i})
    return jsonify({"index": None})


@app.route("/api/lookup")
@protected
def lookup():
    """Jump straight to one combination chosen from the two dropdowns."""
    card_a = request.args.get("a", "")
    card_b = request.args.get("b", "")
    orient_a = request.args.get("oa", "U")
    orient_b = request.args.get("ob", "U")
    if card_a not in CARDS_BY_ID or card_b not in CARDS_BY_ID or card_a == card_b:
        return jsonify({"error": "cartes invalides"}), 400
    if orient_a not in ORIENTATIONS or orient_b not in ORIENTATIONS:
        return jsonify({"error": "orientation invalide"}), 400
    # Pairs are stored with the lower-numbered card first.
    if card_a > card_b:
        card_a, card_b = card_b, card_a
        orient_a, orient_b = orient_b, orient_a
    key = f"{card_a}{orient_a}-{card_b}{orient_b}"
    return jsonify({"index": COMBO_INDEX[key]})


@app.route("/api/cards")
@protected
def api_cards():
    return jsonify(CARDS)


@app.route("/api/progress")
@protected
def api_progress():
    known = filled_keys()
    per_phase = [0] * len(PHASES)
    for key in known:
        per_phase[COMBOS[COMBO_INDEX[key]]["phase"]] += 1
    summary = progress_summary(known)
    summary["phases"] = [
        {"label": label, "done": per_phase[i], "total": TOTAL // len(PHASES)}
        for i, (_, _, label) in enumerate(PHASES)
    ]
    return jsonify(summary)


# ---------------------------------------------------------------------- export

def label_for(card_id, orientation):
    name = CARDS_BY_ID[card_id]["name"]
    return f"{name} renversé" if orientation == "R" else name


@app.route("/export.csv")
@protected
def export_csv():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "cle", "carte_1", "orientation_1", "carte_2", "orientation_2",
            "amour", "argent", "projet_travail", "famille_entourage", "modifie_le",
        ]
    )
    for row in all_entries():
        writer.writerow(
            [
                row["combo_key"],
                CARDS_BY_ID[row["card_a"]]["name"],
                "renversée" if row["orient_a"] == "R" else "endroit",
                CARDS_BY_ID[row["card_b"]]["name"],
                "renversée" if row["orient_b"] == "R" else "endroit",
                row["amour"], row["argent"], row["projet"], row["famille"],
                row["updated_at"],
            ]
        )
    return Response(
        "﻿" + buffer.getvalue(),  # BOM so Excel/Numbers read the accents
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=combinaisons.csv"},
    )


@app.route("/export.json")
@protected
def export_json():
    rows = []
    for row in all_entries():
        rows.append(
            {
                "key": row["combo_key"],
                "cards": [
                    label_for(row["card_a"], row["orient_a"]),
                    label_for(row["card_b"], row["orient_b"]),
                ],
                "amour": row["amour"],
                "argent": row["argent"],
                "projet_travail": row["projet"],
                "famille_entourage": row["famille"],
                "updated_at": row["updated_at"],
            }
        )
    return Response(
        json.dumps(rows, ensure_ascii=False, indent=2),
        mimetype="application/json; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=combinaisons.json"},
    )


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5055)), debug=True)
