#!/usr/bin/env python3
"""Charts that need geography or a time axis, written into index.html.

Each figure is written between a pair of markers, so the prose around it stays
hand-written and the numbers inside it can never drift from the database:

    <!-- ATLAS:lives -->  ... <!-- /ATLAS:lives -->

    python3 generate-atlas.py [--check]

No chart library. Every figure is SVG assembled here, which is the same
constraint the rest of the page works under.
"""
import collections
import math
import os
import re
import sqlite3
import sys

DB = os.path.expanduser("~/.local/share/familysearch-pp-cli/data.db")
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "index.html")

W = 1000
YEAR_RE = re.compile(r"\b(1[0-9]\d\d|20\d\d)\b")

# Rules drawn across the time charts. Wars the family actually appears in, plus
# the two landings that bracket the record.
EVENTS = [
    (1620, "the Mayflower", "point"),
    (1675, "King Philip's War", "point"),
    (1692, "Salem", "point"),
    (1775, "the Revolution", "band", 1783),
    (1861, "the Civil War", "band", 1865),
    (1917, "the First World War", "band", 1918),
    (1941, "the Second World War", "band", 1945),
]


def connect(path):
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        return con
    except sqlite3.OperationalError:
        return sqlite3.connect(path)


def first_year(*values):
    for v in values:
        m = YEAR_RE.findall(v or "")
        if m:
            return int(m[0])
    return None


def lifespan(row):
    """(born, died) as years, from the dated fields or the lifespan string."""
    years = YEAR_RE.findall(row["lifespan"] or "")
    born = first_year(row["birth_date"]) or (int(years[0]) if years else None)
    died = first_year(row["death_date"]) or (int(years[1]) if len(years) > 1 else None)
    return born, died


def in_america(lat, lon):
    return lat is not None and lon is not None and -170 < lon < -50 and 15 < lat < 72


def load():
    db = connect(DB)
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute(
        "SELECT pid, name, gender, lifespan, birth_date, death_date, birth_place, "
        "death_place, birth_lat, birth_lon, death_lat, death_lon, generation "
        "FROM fs_persons WHERE deleted=0")]
    db.close()
    return rows


def lives_chart(rows):
    """One hairline per ancestor who died in America, over the events they lived through.

    Sorted by birth year, so the shape of the block is the shape of the family:
    a wide band through the colonial century, thinning to a handful of lines by
    the twentieth.
    """
    people = []
    for r in rows:
        born, died = lifespan(r)
        if not born or not died or died < born or died - born > 110:
            continue
        # A death in America before Jamestown is a place-name artefact, not a life.
        if not in_america(r["death_lat"], r["death_lon"]) or died < 1607:
            continue
        people.append((born, died))
    people.sort()

    lo, hi = 1560, 2000
    pad_l, pad_r = 116, 26
    top = 84
    span = W - pad_l - pad_r
    row_h = 0.46
    height = top + len(people) * row_h + 46
    x = lambda year: pad_l + span * (year - lo) / (hi - lo)

    out = []
    for year, label, kind, *rest in EVENTS:
        if kind == "band":
            x1, x2 = x(year), x(rest[0])
            out.append(f'<rect x="{x1:.1f}" y="{top}" width="{max(x2 - x1, 1.5):.1f}" '
                       f'height="{len(people) * row_h:.1f}" fill="var(--color-accent-600)" '
                       f'opacity="0.13"/>')
        else:
            out.append(f'<line x1="{x(year):.1f}" y1="{top}" x2="{x(year):.1f}" '
                       f'y2="{top + len(people) * row_h:.1f}" '
                       f'stroke="var(--color-neutral-500)" stroke-width="1" '
                       f'stroke-dasharray="2 3" opacity="0.5"/>')

    for i, (born, died) in enumerate(people):
        y = top + i * row_h
        out.append(f'<line x1="{x(born):.2f}" y1="{y:.2f}" x2="{x(died):.2f}" y2="{y:.2f}" '
                   f'stroke="var(--color-accent-800)" stroke-width="0.42" opacity="0.5"/>')

    # How many of these people were alive in each event year.
    alive = {}
    for year, label, kind, *rest in EVENTS:
        alive[year] = sum(1 for b, d in people if b <= year <= d)

    # Seven events, three of them bunched in the last eighty years of the axis.
    # Alternating two rows is not enough -- the Civil War and the Second World
    # War overprinted each other -- so labels are measured and dropped into the
    # first row where they do not collide with anything already placed.
    def width(label, count):
        return max(len(label) * 6.0, len(f"{count} alive") * 5.5) + 10

    placed, rows_used = [], []
    for year, label, kind, *rest in EVENTS:
        w = width(label, alive[year])
        anchor = "end" if x(year) + w > W - pad_r else "start"
        dx = -4 if anchor == "end" else 4
        x1 = x(year) - w + 4 if anchor == "end" else x(year)
        x2 = x1 + w
        row = 0
        while any(row == r and not (x2 < a or x1 > b) for r, a, b in placed):
            row += 1
        placed.append((row, x1, x2))
        rows_used.append((year, label, anchor, dx, row))

    depth = max(r for *_, r in rows_used) + 1
    labels = []
    for year, label, anchor, dx, row in rows_used:
        base = top - 14 - (depth - 1 - row) * 30
        labels.append(f'<line x1="{x(year):.1f}" y1="{base + 4:.0f}" x2="{x(year):.1f}" '
                      f'y2="{top}" stroke="var(--color-neutral-400)" stroke-width="0.75" '
                      f'opacity="0.6"/>')
        labels.append(f'<text x="{x(year) + dx:.1f}" y="{base - 14:.0f}" '
                      f'text-anchor="{anchor}" class="lv-ev">{label}</text>')
        labels.append(f'<text x="{x(year) + dx:.1f}" y="{base:.0f}" text-anchor="{anchor}" '
                      f'class="lv-n">{alive[year]} alive</text>')

    axis_y = top + len(people) * row_h + 20
    axis = "".join(
        f'<text x="{x(t):.1f}" y="{axis_y + 12}" text-anchor="middle" class="ax">{t}</text>'
        for t in range(1600, 2001, 50))

    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} {height:.0f}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="One horizontal line per ancestor who died in America, {len(people)} of
         them, each running from birth year to death year and sorted by birth. Shaded bands
         mark the Revolution, the Civil War and the two World Wars. The block is widest
         through the seventeenth and eighteenth centuries and narrows to a few lines by the
         twentieth, with {alive[1775]} alive at the Revolution and {alive[1861]} at the
         Civil War.">
      {"".join(labels)}
      {"".join(out)}
      <line x1="{pad_l}" y1="{axis_y}" x2="{W - pad_r}" y2="{axis_y}"
            stroke="var(--color-divider)" stroke-width="1"/>
      {axis}
    </svg>
    <figcaption>Every ancestor who died in America, one line each, birth to death,
    ordered by year of birth. {len(people)} lives. The shaded columns are the wars:
    <b>{alive[1775]}</b> of these people were alive when the Revolution began and
    <b>{alive[1861]}</b> when the Civil War did. Read the right-hand edge — the family does
    not get smaller, the record does, because the generations nearest the present are the
    ones still alive or too recent to be here.</figcaption>
  </figure>"""


COLONIES = [
    ("Massachusetts", ("Massachusetts", "Plymouth Colony", "Massachusetts Bay")),
    ("Connecticut", ("Connecticut",)),
    ("Rhode Island", ("Rhode Island",)),
    ("New Hampshire", ("New Hampshire",)),
    ("Maine", ("Maine",)),
    ("Vermont", ("Vermont",)),
    ("New York", ("New York",)),
    ("New Jersey", ("New Jersey",)),
    ("Pennsylvania", ("Pennsylvania",)),
    ("Virginia", ("Virginia", "West Virginia")),
    ("Ohio", ("Ohio",)),
    ("Indiana / Illinois", ("Indiana", "Illinois")),
    ("Iowa / Kansas", ("Iowa", "Kansas", "Nebraska", "Missouri")),
    ("Michigan / Wisconsin", ("Michigan", "Wisconsin")),
    ("Oregon", ("Oregon",)),
    ("California / Arizona", ("California", "Arizona", "Nevada", "Washington")),
]


def occupancy_chart(rows):
    """Where the family was, by colony or state, in fifty-year slices.

    A person occupies a cell when they died in that place inside that slice.
    Reading down a column shows the frontier moving; reading across a row shows
    how long the family stayed put, which in New England is most of the record.
    """
    lo, hi, step = 1600, 2000, 50
    buckets = list(range(lo, hi, step))
    grid = collections.Counter()
    for r in rows:
        born, died = lifespan(r)
        if not died or died < 1607 or not in_america(r["death_lat"], r["death_lon"]):
            continue
        place = r["death_place"] or ""
        name = next((label for label, keys in COLONIES if any(k in place for k in keys)), None)
        if not name:
            continue
        slot = min(max((died - lo) // step * step + lo, lo), hi - step)
        grid[(name, slot)] += 1

    used = [label for label, _ in COLONIES if any(grid[(label, b)] for b in buckets)]
    peak = max(grid.values()) if grid else 1
    pad_l, top, cell, gap = 168, 42, 46, 3
    width = pad_l + len(buckets) * (cell + gap)
    height = top + len(used) * (cell * 0.62 + gap) + 26
    rows_svg, labels = [], []
    for i, label in enumerate(used):
        y = top + i * (cell * 0.62 + gap)
        labels.append(f'<text x="{pad_l - 12}" y="{y + 19}" text-anchor="end" '
                      f'class="oc-row">{label}</text>')
        for j, b in enumerate(buckets):
            n = grid[(label, b)]
            x = pad_l + j * (cell + gap)
            # Square-root scaling: a linear ramp makes Massachusetts the only
            # visible cell on the whole grid.
            op = 0 if not n else 0.12 + 0.78 * math.sqrt(n / peak)
            rows_svg.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell * 0.62:.0f}" '
                            f'rx="1.5" fill="var(--color-accent-700)" opacity="{op:.3f}"/>')
            if n:
                fill = "#fff" if op > 0.55 else "var(--ink-70)"
                rows_svg.append(f'<text x="{x + cell / 2:.0f}" y="{y + 19}" '
                                f'text-anchor="middle" class="oc-n" fill="{fill}">{n}</text>')
    for j, b in enumerate(buckets):
        labels.append(f'<text x="{pad_l + j * (cell + gap) + cell / 2:.0f}" y="{top - 12}" '
                      f'text-anchor="middle" class="ax">{b}s</text>')
    total = sum(grid.values())
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {width:.0f} {height:.0f}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Grid of colonies and states against fifty-year periods, shaded by how
         many ancestors died in each. Massachusetts dominates the seventeenth and
         eighteenth centuries. Cells appear in Vermont and Ohio around 1800, in the
         Midwest by the mid nineteenth century, and in Oregon and the far west last.">
      {"".join(labels)}
      {"".join(rows_svg)}
    </svg>
    <figcaption>Where they died, by place and half-century. {total} ancestors placed.
    Shading is the square root of the count, because on a straight scale Massachusetts is
    the only cell you can see. The staircase from the top left to the bottom right is the
    whole inland migration in one picture, and the gap between the New England rows going
    quiet and the western rows lighting up is about two hundred years.</figcaption>
  </figure>"""


def flow_map(rows):
    """Minard-style: where the family physically moved, thickness by how many.

    Region positions are the mean of the actual death coordinates in that
    region, so the map is drawn from the data rather than from an atlas. There
    is no coastline, deliberately -- the shape that matters is the set of
    routes, and a traced outline would be decoration this page cannot source.
    """
    def region(place):
        return next((label for label, keys in COLONIES if any(k in (place or "") for k in keys)),
                    None)

    flows, points, ocean = collections.Counter(), collections.defaultdict(list), 0
    for r in rows:
        born, died = lifespan(r)
        if not died or died < 1607 or not in_america(r["death_lat"], r["death_lon"]):
            continue
        dest = region(r["death_place"])
        if dest:
            points[dest].append((r["death_lat"], r["death_lon"]))
        if not in_america(r["birth_lat"], r["birth_lon"]):
            if r["birth_lat"] is not None:
                ocean += 1
            continue
        src = region(r["birth_place"])
        if src and dest and src != dest:
            flows[(src, dest)] += 1

    cent = {k: (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v))
            for k, v in points.items() if len(v) >= 2}
    flows = collections.Counter({k: v for k, v in flows.items()
                                 if k[0] in cent and k[1] in cent})

    lats = [c[0] for c in cent.values()]
    lons = [c[1] for c in cent.values()]
    pad, top, right = 84, 96, 210
    w, h = W - pad - right, 470
    lo_x, hi_x = min(lons) - 2, max(lons) + 2
    lo_y, hi_y = min(lats) - 2, max(lats) + 2
    px = lambda lon: pad + w * (lon - lo_x) / (hi_x - lo_x)
    py = lambda lat: top + h * (hi_y - lat) / (hi_y - lo_y)

    arcs = []
    for (a, b), n in sorted(flows.items(), key=lambda kv: -kv[1]):
        x1, y1 = px(cent[a][1]), py(cent[a][0])
        x2, y2 = px(cent[b][1]), py(cent[b][0])
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy) or 1
        bow = min(dist * 0.18, 54)
        cx, cy = mx - dy / dist * bow, my + dx / dist * bow
        arcs.append(f'<path d="M {x1:.1f} {y1:.1f} Q {cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f}" '
                    f'fill="none" stroke="var(--color-accent-600)" '
                    f'stroke-width="{0.7 + 2.6 * math.sqrt(n):.2f}" opacity="0.42" '
                    f'stroke-linecap="round"/>')

    dots, names = [], []
    weight = collections.Counter()
    for (a, b), n in flows.items():
        weight[a] += n
        weight[b] += n
    for k, (lat, lon) in sorted(cent.items(), key=lambda kv: -len(points[kv[0]])):
        x, y = px(lon), py(lat)
        rr = 2.6 + math.sqrt(len(points[k])) * 0.62
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rr:.1f}" '
                    f'fill="var(--color-accent-800)" opacity="0.9"/>')
        if len(points[k]) >= 4 or weight[k]:
            anchor, dx = ("end", -rr - 5) if lon > -75 else ("start", rr + 5)
            names.append(f'<text x="{x + dx:.1f}" y="{y + 4:.1f}" text-anchor="{anchor}" '
                         f'class="fm-lab">{k} <tspan class="fm-n">{len(points[k])}</tspan></text>')

    # The ocean crossing dwarfs every internal route and has to be on the page,
    # or the map quietly implies the family started in Massachusetts.
    oy = top + h + 40
    ocean_arc = (f'<path d="M {W - right + 120:.0f} {oy:.0f} Q {W - right + 20:.0f} '
                 f'{oy - 34:.0f} {px(cent["Massachusetts"][1]):.0f} '
                 f'{py(cent["Massachusetts"][0]):.0f}" fill="none" '
                 f'stroke="var(--color-neutral-700)" stroke-width="9" opacity="0.3"/>')
    ocean_lab = (f'<text x="{W - right + 124:.0f}" y="{oy + 4:.0f}" class="fm-lab">'
                 f'from across the Atlantic <tspan class="fm-n">{ocean}</tspan></text>')
    total = sum(flows.values())
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} {oy + 40:.0f}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Flow map of ancestral movement across North America. Each dot is a
         colony or state placed at the average of the death coordinates recorded there, and
         each arc is a move from birthplace to place of death, thickness by number of
         people. The heaviest routes are all short and inside New England; a thin set runs
         west to Ohio, the Midwest and Oregon. A separate heavy arc marks {ocean} people who
         arrived across the Atlantic.">
      {ocean_arc}{"".join(arcs)}{"".join(dots)}{"".join(names)}{ocean_lab}
    </svg>
    <figcaption>Movement inside North America: {total} people whose birthplace and place of
    death are in different colonies or states, on {len(flows)} routes. Dots sit at the mean
    of the coordinates actually recorded in each place, and are sized by how many ancestors
    died there. The thickest line on the map is Massachusetts to Connecticut. Almost every
    heavy route is under two hundred miles — this family moved constantly and hardly went
    anywhere, for six generations, until it did.</figcaption>
  </figure>"""


def atlas_chart(rows):
    """One small map per generation, same projection and extent throughout.

    Holding the frame fixed is the whole point: the cloud of dots does not
    change shape because the map moved, it changes because the family did.
    """
    pts = collections.defaultdict(list)
    for r in rows:
        born, died = lifespan(r)
        if not died or died < 1607 or r["generation"] is None:
            continue
        if in_america(r["death_lat"], r["death_lon"]):
            pts[r["generation"]].append((r["death_lat"], r["death_lon"]))

    gens = sorted([g for g, v in pts.items() if len(v) >= 8], reverse=True)
    if not gens:
        return "  <!-- no generation has enough placed deaths -->"

    allp = [p for g in gens for p in pts[g]]
    lo_y, hi_y = min(p[0] for p in allp) - 1.5, max(p[0] for p in allp) + 1.5
    lo_x, hi_x = min(p[1] for p in allp) - 1.5, max(p[1] for p in allp) + 1.5

    cols = 5
    cw, ch, gap, lab = 176, 116, 16, 30
    rows_n = math.ceil(len(gens) / cols)
    width = cols * cw + (cols - 1) * gap
    height = rows_n * (ch + lab + gap)

    cells = []
    for i, g in enumerate(gens):
        ox = (i % cols) * (cw + gap)
        oy = (i // cols) * (ch + lab + gap) + lab
        px = lambda lon: ox + cw * (lon - lo_x) / (hi_x - lo_x)
        py = lambda lat: oy + ch * (hi_y - lat) / (hi_y - lo_y)
        cells.append(f'<rect x="{ox}" y="{oy}" width="{cw}" height="{ch}" fill="none" '
                     f'stroke="var(--color-divider)" stroke-width="1"/>')
        cells.append(f'<text x="{ox}" y="{oy - 14}" class="at-g">generation {g}</text>')
        cells.append(f'<text x="{ox + cw}" y="{oy - 14}" text-anchor="end" '
                     f'class="at-n">{len(pts[g])}</text>')
        for lat, lon in pts[g]:
            cells.append(f'<circle cx="{px(lon):.1f}" cy="{py(lat):.1f}" r="1.9" '
                         f'fill="var(--color-accent-700)" opacity="0.42"/>')
    span = f"{min(gens)}–{max(gens)}"
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {width} {height}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Small multiple maps, one per generation from {max(gens)} back to
         {min(gens)}, all on the same extent of North America. The early panels are a tight
         cluster on the New England coast. Later panels spread inland and then jump to the
         Pacific coast, with far fewer points as the record thins toward the present.">
      {"".join(cells)}
    </svg>
    <figcaption>One panel per generation, {span}, every panel on the same map extent so the
    panels can be compared directly. Each dot is an ancestor who died at that spot. Watch
    the cloud sit still on the New England coast for six panels, then loosen, then throw a
    few points at the far edge. The panels get emptier as they approach the present because
    the record does, not because the family did.</figcaption>
  </figure>"""


TITLE_RE = (r"(?:Capt|Captain|Rev|Dr|Lt|Lieut|Deacon|Hon|Sgt|Col|Sir|Lady|Elder|Ensign|"
            r"Gov|Governor|King|Queen|Brig|Gen|General|Maj|Major|Mrs|Mr|Miss|Baroness|"
            r"Baron|Earl|Duke|Duchess|Countess|Count|Lord|Prince|Princess)")
SUFFIX_RE = (r"(?:Sr|Jr|Snr|Jnr|Esq|II|III|IV|V|VI|VII|VIII|IX|X|\d+(?:st|nd|rd|th))")
PARTICLES = {"de", "del", "van", "von", "der", "den", "le", "la", "du", "des",
             "of", "mac", "mc", "o", "fitz", "st"}

# Surnames the parser produces only from broken records, where a given name sits
# in the final position because the real family name was never entered.
GIVEN_NAME_ARTEFACTS = {"William", "John", "Thomas", "Robert", "Richard", "Henry",
                        "Elizabeth", "Margaret", "Mary", "Anne", "Ann", "James"}


def surname(name):
    """The family name, with titles, suffixes and parentheticals removed.

    Written because the raw field is not usable for counting: 'Sr.' and 'Jr.'
    were among the commonest 'surnames' in the tree until this ran. Particles
    are kept attached, so 'de la Vigne' stays one name rather than 'Vigne'.
    Returns None rather than guessing when a record holds only one name.
    """
    if not name:
        return None
    n = re.sub(r"\(.*?\)", "", re.sub(r"\*+", "", name))
    n = re.sub(r"\b" + TITLE_RE + r"\.?\s+", "", n)
    n = re.sub(r"\s+of\s+[A-Z].*$", "", n)          # "... of Halkhead"
    for _ in range(3):
        n = re.sub(r"[\s,]+" + SUFFIX_RE + r"\.?\s*$", "", n).strip()
    n = re.sub(r"\s+", " ", n).strip(" ,.")
    tokens = n.split()
    if len(tokens) < 2:
        return None
    i = len(tokens) - 1
    while i > 0 and tokens[i - 1].lower().strip(".") in PARTICLES:
        i -= 1
    out = " ".join(tokens[i:])
    return out if len(out) > 1 and out[0].isupper() else None


def surnames_chart(rows):
    """When each family name entered this record and when it left it.

    In a pedigree a surname survives only while sons carry it. The moment the
    descent passes through a daughter the name stops being an ancestor's name,
    which is why almost every bar on this chart ends in a woman.
    """
    people = collections.defaultdict(list)
    for r in rows:
        # Living people are excluded outright. A dot on this axis is a birth
        # year, and the record does not publish those for the living.
        if "Living" in (r["lifespan"] or ""):
            continue
        s = surname(r["name"])
        born, _ = lifespan(r)
        if s and born:
            people[s].append((born, r["gender"], r["name"], r["generation"]))

    # Sort on the year alone: generation can be None and would break a plain
    # tuple comparison on ties.
    fams = {s: sorted(v, key=lambda t: t[0]) for s, v in people.items() if len(v) >= 5}
    fams = {s: v for s, v in fams.items() if v[-1][0] >= 1550}
    # Given names that reach this point are always a mangled record, never a
    # family: "Howell T William" and its kind. Counting them would put a name
    # on the chart that nobody in this tree was ever called.
    fams = {s: v for s, v in fams.items() if s not in GIVEN_NAME_ARTEFACTS}
    order = sorted(fams, key=lambda s: (-fams[s][-1][0], s))[:46]

    lo, hi = 1500, 2000
    pad_l, pad_r, top, row_h = 132, 118, 40, 15.5
    span = W - pad_l - pad_r
    height = top + len(order) * row_h + 34
    x = lambda y: pad_l + span * (min(max(y, lo), hi) - lo) / (hi - lo)

    out, ended_female = [], 0
    for i, s in enumerate(order):
        v = fams[s]
        y = top + i * row_h
        first, last = v[0][0], v[-1][0]
        term_gender = v[-1][1]
        if term_gender == "FEMALE":
            ended_female += 1
        out.append(f'<line x1="{x(first):.1f}" y1="{y:.1f}" x2="{x(last):.1f}" y2="{y:.1f}" '
                   f'stroke="var(--color-accent-600)" stroke-width="3.4" opacity="0.30" '
                   f'stroke-linecap="round"/>')
        for born, gender, _, _ in v:
            out.append(f'<circle cx="{x(born):.1f}" cy="{y:.1f}" r="1.7" '
                       f'fill="var(--color-accent-800)" opacity="0.55"/>')
        colour = ("var(--color-accent)" if term_gender == "FEMALE"
                  else "var(--color-neutral-800)")
        out.append(f'<circle cx="{x(last):.1f}" cy="{y:.1f}" r="3.5" fill="{colour}"/>')
        out.append(f'<text x="{pad_l - 10}" y="{y + 4:.1f}" text-anchor="end" '
                   f'class="sn-name">{s}</text>')
        # "Carries on" would be a claim the chart cannot support: living people
        # are excluded, so a name ending on a man usually means his daughter is
        # simply not drawn. Say what is true instead -- the record stops.
        out.append(f'<text x="{x(last) + 9:.1f}" y="{y + 4:.1f}" class="sn-end">'
                   f'{"ends in a daughter" if term_gender == "FEMALE" else "record stops"}'
                   f'</text>')

    axis_y = top + len(order) * row_h + 12
    axis = "".join(
        f'<text x="{x(t):.1f}" y="{axis_y + 13}" text-anchor="middle" class="ax">{t}</text>'
        for t in range(1550, 2001, 50))
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} {height:.0f}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="One bar per family name, running from the birth year of its earliest
         ancestor to its latest, sorted by when the name leaves the record. A filled dot
         marks the last person to carry it. Almost every dot marks a woman, because a
         surname stops being an ancestral name as soon as the descent passes through a
         daughter.">
      {"".join(out)}
      <line x1="{pad_l}" y1="{axis_y}" x2="{W - pad_r}" y2="{axis_y}"
            stroke="var(--color-divider)" stroke-width="1"/>
      {axis}
    </svg>
    <figcaption>The {len(order)} family names that stayed in this record longest, each
    drawn from its earliest ancestor's birth to its latest. Small dots are people; the
    filled dot is the last one. <b>{ended_female} of these {len(order)} names end in a
    woman</b> — the daughter who married, took another name, and carried the line onward
    under it.</figcaption>
  </figure>"""


CHARTS = {"lives": lives_chart, "occupancy": occupancy_chart, "flow": flow_map,
          "atlas": atlas_chart, "surnames": surnames_chart}


def main():
    rows = load()
    page = open(PAGE, encoding="utf-8").read()
    written = []
    for name, fn in CHARTS.items():
        begin, end = f"<!-- ATLAS:{name} -->", f"<!-- /ATLAS:{name} -->"
        if begin not in page:
            print(f"  (no marker for {name}, skipped)")
            continue
        block = fn(rows)
        page = re.sub(re.escape(begin) + r".*?" + re.escape(end),
                      lambda _: f"{begin}\n{block}\n{end}", page, flags=re.S)
        written.append(name)

    if "--check" in sys.argv:
        if open(PAGE, encoding="utf-8").read() != page:
            print("atlas figures are stale — run generate-atlas.py")
            sys.exit(1)
        print("atlas figures are current")
        return
    open(PAGE, "w", encoding="utf-8").write(page)
    print(f"atlas written · {', '.join(written) if written else 'nothing'}")


if __name__ == "__main__":
    main()
