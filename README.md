# Combinaisons

Data-collection app for pairs of major arcana. One combination at a time — the
two cards, each with its French name and orientation — and four fields (Amour,
Argent, Projet/Travail, Famille/Entourage), autosaved as they are typed.

**231 pairs × 4 orientations = 924 combinations.** They are served in four
series so a usable dataset exists early:

1. both cards upright (231)
2. second card reversed (231)
3. first card reversed (231)
4. both reversed (231)

Within a series the pairs are shuffled. Unshuffled, the first 21 combinations
all start with Le Fou and the next 20 with Le Bateleur, which turns the task
into pattern-matching; shuffled, the longest run sharing a first card is 3.

The shuffle is seeded (`SHUFFLE_SEED` in `app.py`) and **must never change**: a
position is what the resume pointer, the `#index` in the URL and any shared link
refer to. Rows are keyed by `combo_key` rather than by position, so reordering
cannot corrupt data that already exists — but it would strand every saved link.

Nothing has to be finished in one sitting: progress is stored per combination,
and the dropdowns jump straight to a specific pair.

Opening the page picks a starting card in this order: an explicit `#index` in
the URL, then the last card visited in that browser (kept in `localStorage`),
then the first combination that is not yet complete. So a bookmark reopens where
she stopped, and a brand-new device starts at the work front rather than at
card 0.

To revisit something she already wrote, the *Mes cartes remplies* panel lists
her entries newest-first — the two card names, a snippet of what she wrote, and
a ✓ (complete) or *à finir* badge — with a search box to filter by card. Tapping
one opens that combination to edit. It reads from `/api/filled` and never writes.

All four fields are required: *Suivante* refuses to advance until they are
filled, and marks the empty ones. The other three ways off a card are not
validated, by design — *Précédente* goes back, *Passer* moves on without
answering, and *Prochaine vide* jumps to the next combination that is not yet
complete (a half-filled one counts as unfinished).

The footer ranks the four by weight: *Suivante* is the filled dark button,
*Précédente* the outlined one beside it, and *Passer* / *Prochaine vide* sit
behind a divider as quiet text buttons.

## Compliments

Every time a card is completed and *Suivante* moves on, a short compliment for
Corinne appears above the buttons for a couple of seconds. They are drawn from a
bag in `templates/index.html` (`COMPLIMENTS`), so none repeats until the whole
list has had its turn — add or reword them freely there.

## The little party (every 50 cards)

Each time the count of completed cards crosses a multiple of 50, a full-screen
celebration appears: a photo, floating hearts, "Je t'aime, Corinne" and the
signature "— Richard Lee". It fires once per milestone (per browser), never on
reloads or when editing an older card, and a tap or ~9s dismisses it.

Photos live in `static/richard/` (`.jpg`/`.png`) and one is chosen at random
each time. With the folder empty the party still runs, showing a heart where the
photo would be. `FETE_TOUS` in `templates/index.html` sets the interval (50).

## Running it locally

```bash
./venv/bin/python app.py
```

Then open http://localhost:5055. Without `DATABASE_URL` it writes to
`combinaisons.db` (SQLite) next to `app.py`.

## Deploying

The app is host-agnostic (Procfile + `render.yaml` included). Two environment
variables matter:

| Variable | What it does |
| --- | --- |
| `ACCESS_CODE` | Shared code asked for on the login page. Leave unset and the app is open to anyone with the URL. |
| `SECRET_KEY` | Signs the session cookie. Any long random string. |
| `DATABASE_URL` | Postgres connection string. **Set this in production** — see below. |

### Use Postgres in production, not SQLite

On most free tiers the filesystem is wiped on every deploy and restart, so a
SQLite file there will lose the data. Point `DATABASE_URL` at a managed Postgres
(Neon, Supabase, Render Postgres) and the app creates its table on first boot.
`postgres://` URLs are rewritten to `postgresql://` automatically.

Free web tiers also sleep after inactivity, which makes the first page load of
the day slow (~1 minute). That is the tier, not the app.

## Daily email report

At the end of each day an email can go out summarising what Corinne completed
that day — the count, each pairing, and the four fields she wrote. It is sent to
whatever addresses `REPORT_TO` lists (her, you, or both).

The endpoint is `GET /tasks/daily-report`, guarded by `REPORT_TOKEN` (not the
login). `?dry=1` returns the rendered report **without sending** — safe to open
in a browser to preview. `?date=YYYY-MM-DD` reports a specific local day. An
empty day sends nothing rather than nagging.

Sending uses [Resend](https://resend.com) (~100 emails/day free) via its REST
API — no extra Python dependency. Set `RESEND_API_KEY`, `REPORT_FROM` (a sender
on a domain you have verified with Resend) and `REPORT_TO`. With those unset the
endpoint still previews but refuses to send.

The daily trigger is a **free GitHub Actions schedule** (`.github/workflows/
daily-report.yml`), so no always-on server is needed. Add the app URL's
`REPORT_TOKEN` as a repository secret (Settings → Secrets and variables →
Actions). Cron runs in UTC with no daylight-saving shift, so 19:00 UTC is 21:00
in Paris in summer, 20:00 in winter. The workflow also has a manual *Run
workflow* button for testing.

## Getting the data out

- `/export.csv` — one row per filled combination, UTF-8 with a BOM so Numbers
  and Excel read the accents correctly.
- `/export.json` — the same data with the card names already resolved.

Both are linked at the bottom of the page under *Aller à une combinaison
précise, et exports*.

## The card images

`static/cards/` holds one image per arcanum, named by Marseille number
(`00.png` = Le Fou … `21.png` = Le Monde).

- 19 of them are cut out of `mini-tarot-cards-printable.pdf` by
  `tools/extract_cards.py`, which renders the PDF through Quartz at 8x, finds
  the card frames and crops them.
- La Force, La Mort and L'Étoile are absent from that sheet, so
  `tools/generate_cards.py` draws them as SVG in a matching style.

That deck numbers the cards the Rider way (Justice XI, Strength VIII) rather
than the Marseille way (Justice VIII, Force XI), and its titles are in English.
The app therefore shows only the French name under each card, never a numeral,
so nothing contradicts what is printed on the image. To swap in different
artwork, drop a `NN.png`/`NN.svg` into `static/cards/` — the app picks up
whichever extension it finds.

`tools/build_card_data.py` regenerates `data/cards.json` with the French card
names. It also carries over the keyword line for each card from the main app's
`tarot.csv`; the app does not show those — under each card it prints only the
name and the orientation — but they stay in the data in case they are wanted.
