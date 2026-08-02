# Deviations from `frontend-spec.md`

The spec was written against placeholder content (§10: "All current copy is
placeholder"). Applying it to the real record required four changes.

### 1. Five epochs, not four

The spec describes four migration epochs on invented dates (1743–present). The
actual record contains **five** distinct crossings, on different dates:

| № | Crossing | Years | People |
| --- | --- | --- | --- |
| I | The Great Migration | 1620–1640 | 488 |
| II | New Netherland | 1624–1664 | 27 |
| III | The Palatines | 1709–1760 | 25 |
| IV | The Ulster Scots | 1718–1775 | 12 |
| V | The Industrial Crossing | 1840–1870 | 8 |

The structural pattern the spec defines — colophon divider followed by epoch
body, ghost roman numeral, index group — extends to five without modification.

### 1b. A second spine: the inland migration

The spec organises the page around arrivals only. The record does not support that
reading — crossing the Atlantic was one event, and settling the continent took
another 230 years. The page now carries both:

- **They crossed once. Then they walked.** — a stacked-bar chart of each
  generation's American deaths by region, plus a nine-stop frontier ladder.
  The chart is the argument: New England holds 85–95% for six generations, then
  falls to 39% in the single step between the eighth generation and the seventh.
- **Paid in western acres** (Ohio, 1788) — promoted out of a subhead inside the
  patriots section, because it is the hinge that break depends on.
- **The Republic of Vermont** (1750s–1791) — the northern frontier leg, and the
  Gores' waypoint between Connecticut and Iowa.

### 2. `<image-slot>` replaced by real `<img>`

Spec §8 mounts every photograph through `<image-slot>`, whose stated purpose is
that "drops persist across reloads" — a canvas affordance of the design tool.
This is a production site with real archive images, so plates use plain `<img>`
inside `figure.plate-fig`, retaining the spec's aspect-ratio vocabulary and the
`.plate` archival grade and mat.

### 3. Plate placement follows what actually exists

The spec assigns a plate to every epoch. Only seven full-resolution images exist,
and all seven belong to one family in the final crossing. Everything else in the
archive is a 200×200 thumbnail.

Rather than upscale thumbnails into 21:9 and 4:5 plates, the large plates appear
only where genuine photographs exist (Crossing V and the third figure spread),
and the 200px images are used at exactly 200px in the figure-spread portrait
column — which the spec already sizes at `200px`. Crossings I–IV carry no large
plate.

This is stated on the page in the provenance note, because the absence is a fact
about the record: the photographic era begins in the 1840s, and no earlier
ancestor left a likeness.

### 4. The accent-filled stat numeral is `1620`

Spec §5 permits exactly one filled accent moment on the light ground: the `1743`
stat numeral. The equivalent figure here is the first landing, `1620`. The
`-0.129em` optical inset the spec specifies for a display numeral leading with
`1` still applies.

### 5. The ~200-word epoch budget was dropped

Spec §10 sets "roughly 200 words per epoch; one paragraph per figure." That budget
was written for placeholder copy. Applied to the real record it summarised away
the material the page exists for — the Mayflower roster, the Great Swamp Fight,
Mary Esty's petition, the violin. The page runs to about 6,200 words.

The spec's structural rules are all still honoured; only the word count is not.

# Additions

- `.skip-link` to the main record.
- The head gates the scroll-reveal's hidden state on `prefers-reduced-motion`
  and `IntersectionObserver` support before first paint, so the page never
  paints content hidden that it cannot then reveal.

## Where the crossing counts come from

The five crossing totals and the `Crossed an ocean` headline are the `crossing_of` classification in `generate-charts.py`, not hand counts. An immigrant is someone born outside America after 1500 who died in America after 1607; the crossing is their birth nation, except that a birth from 1800 is the Industrial Crossing whatever the nation. As of the completed hydration they sum exactly to the headline (488+27+25+12+8 = 560) with nobody unclassified. If they stop summing, the data moved and the page is stale.
