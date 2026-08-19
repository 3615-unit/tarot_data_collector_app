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
