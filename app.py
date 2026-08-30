"""Combinaisons — data collection for pairs of major arcana.

231 pairs x 4 orientations = 924 combinations. One combination is shown at a
time with four fields (Amour, Argent, Projet/Travail, Famille/Entourage) that
autosave as they are typed.

Storage is SQLite locally, Postgres when DATABASE_URL is set.
"""

import csv
import hmac
import io
import json
import os
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, time as dtime, timezone
from functools import wraps
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo

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

# Daily email report (see /tasks/daily-report). All optional: with none set the
# endpoint still renders a dry-run report but refuses to send.
REPORT_TOKEN = os.environ.get("REPORT_TOKEN", "").strip()      # shared secret the scheduler sends
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()  # https://resend.com, ~100 free/day
REPORT_FROM = os.environ.get("REPORT_FROM", "").strip()        # verified sender, e.g. Combinaisons <combinaisons@ton-domaine>
REPORT_TO = os.environ.get("REPORT_TO", "").strip()            # comma-separated recipients
REPORT_TZ = os.environ.get("REPORT_TZ", "Europe/Paris").strip()

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


def richard_images():
    """Photos for the every-50-cards celebration, from static/richard/.

    Not shipped with the app: drop the photos in that folder and one is chosen
    at random each time. Empty folder and the party still runs, just with a
    heart where the photo would be.
    """
    folder = ROOT / "static" / "richard"
    if not folder.is_dir():
        return []
    exts = (".jpg", ".jpeg", ".png", ".webp", ".gif")
    return [
        f"richard/{p.name}"
        for p in sorted(folder.iterdir())
        if p.suffix.lower() in exts
    ]


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

        # `entries` stores card codes (00-21) so it never depends on the French
        # names. This reference table plus the `combinations` view below exist
        # only so the database is legible when browsed directly (in Neon, say):
        # open `combinations` and every row shows real names and orientations.
        # The app itself never reads either — it keeps using `entries`.
        cur.execute(
            "CREATE TABLE IF NOT EXISTS cards (code TEXT PRIMARY KEY, name TEXT NOT NULL)"
        )
        for card in CARDS:
            if using_postgres():
                cur.execute(
                    "INSERT INTO cards (code, name) VALUES (%s, %s) "
                    "ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name",
                    (card["id"], card["name"]),
                )
            else:
                cur.execute(
                    "INSERT OR REPLACE INTO cards (code, name) VALUES (?, ?)",
                    (card["id"], card["name"]),
                )

        # Rebuilt each boot so a renamed card flows through. DROP + CREATE works
        # on both SQLite and Postgres; '' is the SQL escape for a literal quote.
        cur.execute("DROP VIEW IF EXISTS combinations")
        cur.execute(
            """
            CREATE VIEW combinations AS
            SELECT e.combo_key,
                   ca.name AS carte_1,
                   CASE e.orient_a WHEN 'R' THEN 'renversée' ELSE 'à l''endroit' END AS orientation_1,
                   cb.name AS carte_2,
                   CASE e.orient_b WHEN 'R' THEN 'renversée' ELSE 'à l''endroit' END AS orientation_2,
                   e.amour, e.argent, e.projet, e.famille, e.updated_at
            FROM entries e
            JOIN cards ca ON ca.code = e.card_a
            JOIN cards cb ON cb.code = e.card_b
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
    richard = [url_for("static", filename=name) for name in richard_images()]
    return render_template("index.html", total=TOTAL, fields=FIELDS, richard=richard)


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


@app.route("/api/filled")
@protected
def api_filled():
    """Her journal: every combination she has touched, most recent first.

    Powers the "cartes remplies" list so she can find an entry by its cards and
    a snippet of what she wrote, and tap straight back to it — no need to know
    the pair in advance the way the dropdown jump requires.
    """
    items = []
    for row in all_entries():
        combo = COMBOS[COMBO_INDEX[row["combo_key"]]]
        snippet = next(
            (row[f].strip() for f in FIELDS if row[f].strip()), ""
        )
        items.append(
            {
                "index": COMBO_INDEX[row["combo_key"]],
                "card_a": label_for(row["card_a"], row["orient_a"]),
                "card_b": label_for(row["card_b"], row["orient_b"]),
                "complete": all(row[f].strip() for f in FIELDS),
                "snippet": snippet[:80],
                "updated_at": row["updated_at"],
            }
        )
    items.sort(key=lambda it: it["updated_at"] or "", reverse=True)
    return jsonify(items)


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


# ---------------------------------------------------------------- daily report

FIELD_LABELS = {
    "amour": "Amour",
    "argent": "Argent",
    "projet": "Projet / Travail",
    "famille": "Famille / Entourage",
}


def report_tz():
    try:
        return ZoneInfo(REPORT_TZ)
    except Exception:
        return timezone.utc


def day_report(target_date=None):
    """What she completed on `target_date` (her local day; default: today).

    A row counts as "today" if its last save falls inside that local day. Only
    fully-filled combinations are listed — a half-entry is still in progress.
    """
    tz = report_tz()
    day = target_date or datetime.now(tz).date()
    start_utc = datetime.combine(day, dtime.min, tz).astimezone(timezone.utc)
    end_utc = datetime.combine(day, dtime.max, tz).astimezone(timezone.utc)

    items = []
    for row in all_entries():
        stamp = row["updated_at"]
        if not stamp:
            continue
        when = datetime.fromisoformat(stamp)
        if not (start_utc <= when <= end_utc):
            continue
        if not all(row[f].strip() for f in FIELDS):
            continue
        items.append(
            {
                "cards": f'{label_for(row["card_a"], row["orient_a"])}'
                f' + {label_for(row["card_b"], row["orient_b"])}',
                "fields": {f: row[f].strip() for f in FIELDS},
                "when": when.astimezone(tz).strftime("%H:%M"),
            }
        )
    items.sort(key=lambda it: it["when"])
    return {"date": day.isoformat(), "count": len(items), "items": items}


def render_report(report):
    """Plain-text and HTML bodies for the day's work."""
    d = report["date"]
    n = report["count"]
    head = f"{n} carte{'s' if n != 1 else ''} remplie{'s' if n != 1 else ''} le {d}"

    text = [f"Bonjour Corinne,", "", head, ""]
    for it in report["items"]:
        text.append(f'• {it["cards"]}  ({it["when"]})')
        for f in FIELDS:
            text.append(f'    {FIELD_LABELS[f]} : {it["fields"][f]}')
        text.append("")
    text.append("Bravo pour ton travail. 🌙")

    esc = lambda s: (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    html = [
        '<div style="font-family:Georgia,serif;color:#2f2b3d;max-width:640px;margin:auto">',
        '<p>Bonjour Corinne,</p>',
        f'<p style="font-size:18px"><strong>{esc(head)}</strong></p>',
    ]
    for it in report["items"]:
        html.append(
            '<div style="border:1px solid #ded1b8;border-radius:10px;'
            'padding:12px 16px;margin:12px 0;background:#fbf6ec">'
        )
        html.append(
            f'<div style="font-size:16px;margin-bottom:6px">'
            f'<strong>{esc(it["cards"])}</strong> '
            f'<span style="color:#6c6580;font-size:13px">{it["when"]}</span></div>'
        )
        for f in FIELDS:
            html.append(
                f'<div style="margin:4px 0"><span style="color:#6c6580">'
                f'{FIELD_LABELS[f]} :</span> {esc(it["fields"][f])}</div>'
            )
        html.append("</div>")
    html.append('<p>Bravo pour ton travail. 🌙</p></div>')

    subject = f"Combinaisons — {n} carte{'s' if n != 1 else ''} le {d}"
    return subject, "\n".join(text), "\n".join(html)


def send_email(subject, text_body, html_body):
    """Send via Resend's REST API using only the standard library."""
    if not (RESEND_API_KEY and REPORT_FROM and REPORT_TO):
        return False, "email not configured (RESEND_API_KEY / REPORT_FROM / REPORT_TO)"
    recipients = [addr.strip() for addr in REPORT_TO.split(",") if addr.strip()]
    payload = json.dumps(
        {
            "from": REPORT_FROM,
            "to": recipients,
            "subject": subject,
            "text": text_body,
            "html": html_body,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return False, f"{exc.code} {exc.read().decode('utf-8', 'replace')}"
    except Exception as exc:  # network, DNS, timeout
        return False, str(exc)


@app.route("/tasks/daily-report")
def daily_report():
    """Machine-triggered end-of-day email. Guarded by REPORT_TOKEN, not login.

    ?dry=1 renders the report and returns it without sending — safe to open in a
    browser to preview. ?date=YYYY-MM-DD reports a specific local day.
    """
    supplied = request.args.get("token", "")
    if not REPORT_TOKEN or not hmac.compare_digest(supplied, REPORT_TOKEN):
        return jsonify({"error": "unauthorized"}), 401

    target = None
    if request.args.get("date"):
        try:
            target = datetime.strptime(request.args["date"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "date invalide (YYYY-MM-DD)"}), 400

    report = day_report(target)
    subject, text_body, html_body = render_report(report)

    if request.args.get("dry"):
        return jsonify({"would_send": report["count"] > 0, "subject": subject,
                        "report": report, "text": text_body})

    # Nothing to celebrate on an empty day — skip rather than nag.
    if report["count"] == 0:
        return jsonify({"sent": False, "count": 0, "reason": "no cards today"})

    ok, detail = send_email(subject, text_body, html_body)
    status = 200 if ok else 502
    return jsonify({"sent": ok, "count": report["count"], "detail": detail}), status


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5055)), debug=True)
