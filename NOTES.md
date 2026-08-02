# Deviations from `frontend-spec.md`

The spec was written against placeholder content (§10: "All current copy is
placeholder"). Applying it to the real record required four changes.

### 1. Five epochs, not four

The spec describes four migration epochs on invented dates (1743–present). The
actual record contains **five** distinct crossings, on different dates:

| № | Crossing | Years | People |
| --- | --- | --- | --- |
| I | The Great Migration | 1620–1640 | 472 |
| II | New Netherland | 1624–1664 | 16 |
| III | The Palatines | 1709–1760 | 21 |
| IV | The Ulster Scots | 1718–1775 | 12 |
| V | The Industrial Crossing | 1840–1870 | 8 |

The structural pattern the spec defines — colophon divider followed by epoch
body, ghost roman numeral, index group — extends to five without modification.

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

# Additions

- `.skip-link` to the main record.
- The head gates the scroll-reveal's hidden state on `prefers-reduced-motion`
  and `IntersectionObserver` support before first paint, so the page never
  paints content hidden that it cannot then reveal.
