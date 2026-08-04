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
import statistics
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
    """(born, died) as years.

    The lifespan string is positional -- "1687-1687", "-1600", "1840-Deceased" --
    so it has to be split on the dash rather than scanned for years. Reading the
    first year found as the birth year turns 243 records that carry only a death
    year into people who died aged zero, which is how this record briefly
    acquired a few hundred spurious infant deaths.
    """
    text = row["lifespan"] or ""
    left, _, right = text.partition("\u2013")
    if not _:
        left, _, right = text.partition("-")
    born = first_year(row["birth_date"]) or first_year(left)
    died = first_year(row["death_date"]) or first_year(right)
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


def lives_chart(rows, sides):
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
        # A death in America before Jamestown is a place-name artifact, not a life.
        if not in_america(r["death_lat"], r["death_lon"]) or died < 1607:
            continue
        # Ancestors only. The walk pulled in the whole sibling cohort at one
        # generation -- 435 people, every one of them generation 8 -- and
        # counting them here inflated "alive at the Revolution" from 90 to 305.
        side = side_of(r["pid"], sides)
        if side is None:
            continue
        people.append((born, died, side))
    people.sort(key=lambda t: t[0])

    lo, hi = 1560, 2000
    pad_l, pad_r = 116, 26
    top = 84
    span = W - pad_l - pad_r
    row_h = 0.62
    height = top + len(people) * row_h + 78
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

    for i, (born, died, side) in enumerate(people):
        y = top + i * row_h
        color = SIDE_COLOR.get(side, "var(--color-neutral-500)")
        out.append(f'<line x1="{x(born):.2f}" y1="{y:.2f}" x2="{x(died):.2f}" y2="{y:.2f}" '
                   f'stroke="{color}" stroke-width="0.62" opacity="0.72"/>')

    # How many of these people were alive in each event year.
    alive = {}
    for year, label, kind, *rest in EVENTS:
        alive[year] = sum(1 for b, d, _s in people if b <= year <= d)

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
      {legend(pad_l, axis_y + 30)}
      <line x1="{pad_l}" y1="{axis_y}" x2="{W - pad_r}" y2="{axis_y}"
            stroke="var(--color-divider)" stroke-width="1"/>
      {axis}
    </svg>
    <figcaption>Every <em>ancestor</em> who died in America, one line each, birth to death,
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


def occupancy_chart(rows, sides):
    """Where the family was, by colony or state, in fifty-year slices.

    A person occupies a cell when they died in that place inside that slice.
    Reading down a column shows the frontier moving; reading across a row shows
    how long the family stayed put, which in New England is most of the record.
    """
    lo, hi, step = 1600, 2000, 50
    buckets = list(range(lo, hi, step))
    grid = collections.Counter()
    split = collections.defaultdict(collections.Counter)
    for r in rows:
        born, died = lifespan(r)
        if not died or died < 1607 or not in_america(r["death_lat"], r["death_lon"]):
            continue
        if side_of(r["pid"], sides) is None:
            continue
        place = r["death_place"] or ""
        name = next((label for label, keys in COLONIES if any(k in place for k in keys)), None)
        if not name:
            continue
        slot = min(max((died - lo) // step * step + lo, lo), hi - step)
        grid[(name, slot)] += 1
        split[(name, slot)][side_of(r["pid"], sides)] += 1

    used = [label for label, _ in COLONIES if any(grid[(label, b)] for b in buckets)]
    peak = max(grid.values()) if grid else 1
    pad_l, top, cell, gap = 168, 42, 46, 3
    width = max(pad_l + len(buckets) * (cell + gap), 620)
    height = top + len(used) * (cell * 0.62 + gap) + 50
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
            if n:
                # The cell is banded by side, so the color mix reads as
                # composition while the opacity still reads as volume.
                ch2 = cell * 0.62
                oy2 = y
                for key in ("father", "both", "mother", None):
                    part = split[(label, b)][key]
                    if not part:
                        continue
                    hh = ch2 * part / n
                    rows_svg.append(f'<rect x="{x}" y="{oy2:.2f}" width="{cell}" '
                                    f'height="{hh:.2f}" fill="{SIDE_COLOR[key]}" '
                                    f'opacity="{op:.3f}"/>')
                    oy2 += hh
            if n:
                fill = "#fff" if op > 0.62 else "var(--ink-70)"
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
      {legend(0, height - 6)}
    </svg>
    <figcaption>Where they died, by place and half-century. {total} ancestors placed.
    Shading is the square root of the count, because on a straight scale Massachusetts is
    the only cell you can see. The staircase from the top left to the bottom right is the
    whole inland migration in one picture, and the gap between the New England rows going
    quiet and the western rows lighting up is about two hundred years.</figcaption>
  </figure>"""


def flow_map(rows, sides):
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
    route_side = collections.defaultdict(collections.Counter)
    ocean_side = collections.Counter()
    for r in rows:
        born, died = lifespan(r)
        if not died or died < 1607 or not in_america(r["death_lat"], r["death_lon"]):
            continue
        if side_of(r["pid"], sides) is None:
            continue
        dest = region(r["death_place"])
        if dest:
            points[dest].append((r["death_lat"], r["death_lon"]))
        if not in_america(r["birth_lat"], r["birth_lon"]):
            if r["birth_lat"] is not None:
                ocean += 1
                ocean_side[side_of(r["pid"], sides)] += 1
            continue
        src = region(r["birth_place"])
        if src and dest and src != dest:
            flows[(src, dest)] += 1
            route_side[(src, dest)][side_of(r["pid"], sides)] += 1

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
        dominant = route_side[(a, b)].most_common(1)[0][0] if route_side[(a, b)] else None
        arcs.append(f'<path d="M {x1:.1f} {y1:.1f} Q {cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f}" '
                    f'fill="none" stroke="{SIDE_COLOR[dominant]}" '
                    f'stroke-width="{0.7 + 2.6 * math.sqrt(n):.2f}" opacity="0.5" '
                    f'stroke-linecap="round"/>')

    dots, names = [], []
    weight = collections.Counter()
    for (a, b), n in flows.items():
        weight[a] += n
        weight[b] += n

    # New England is a knot at this scale: half a dozen regions inside forty
    # pixels. Labels are pushed apart vertically within their side of the map
    # and joined back to their dot with a leader, rather than printed on top of
    # one another.
    wanted = []
    for k, (lat, lon) in cent.items():
        if len(points[k]) >= 4 or weight[k]:
            wanted.append((k, px(lon), py(lat), 2.6 + math.sqrt(len(points[k])) * 0.62))
    for k, (lat, lon) in sorted(cent.items(), key=lambda kv: -len(points[kv[0]])):
        x, y = px(lon), py(lat)
        rr = 2.6 + math.sqrt(len(points[k])) * 0.62
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rr:.1f}" '
                    f'fill="var(--color-accent-800)" opacity="0.9"/>')

    GAP = 16.0
    eastern = [t for t in wanted if t[1] > W * 0.62]
    western = [t for t in wanted if t[1] <= W * 0.62]

    # The eastern dots overlap each other, so nudging labels apart is not
    # enough -- a label still lands on top of Massachusetts, which at this
    # scale is a 28px disc. The whole cluster gets one label column clear of
    # the rightmost dot, and a leader back to each dot.
    if eastern:
        col = max(x + rr for _k, x, _y, rr in eastern) + 22
        eastern.sort(key=lambda t: t[2])
        placed, prev = [], None
        for k, x, y, rr in eastern:
            ly = y if prev is None else max(y, prev + GAP)
            placed.append((k, ly, x, y, rr))
            prev = ly
        overflow = placed[-1][1] - (top + h + 4)
        if overflow > 0:
            placed = [(k, ly - overflow, x, y, rr) for k, ly, x, y, rr in placed]
        for k, ly, x, y, rr in placed:
            names.append(f'<path d="M {x + rr + 3:.1f} {y:.1f} L {col - 5:.1f} '
                         f'{ly - 4:.1f}" fill="none" stroke="var(--color-neutral-400)" '
                         f'stroke-width="0.7" opacity="0.65"/>')
            names.append(f'<text x="{col:.1f}" y="{ly:.1f}" class="fm-lab">{k} '
                         f'<tspan class="fm-n">{len(points[k])}</tspan></text>')

    # Western dots are far apart; a label beside each is fine.
    western.sort(key=lambda t: t[2])
    prev = None
    for k, x, y, rr in western:
        ly = y if prev is None else max(y, prev + GAP)
        prev = ly
        if abs(ly - y) > 1.5:
            names.append(f'<path d="M {x - rr - 3:.1f} {y:.1f} L {x - rr - 8:.1f} '
                         f'{ly - 4:.1f}" fill="none" stroke="var(--color-neutral-400)" '
                         f'stroke-width="0.7" opacity="0.65"/>')
        names.append(f'<text x="{x - rr - 10:.1f}" y="{ly:.1f}" text-anchor="end" '
                     f'class="fm-lab">{k} <tspan class="fm-n">{len(points[k])}</tspan></text>')

    # The ocean crossing dwarfs every internal route and has to be on the page,
    # or the map quietly implies the family started in Massachusetts.
    oy = top + h + 40
    ocean_x = W - 30
    ocean_arc = (f'<path d="M {ocean_x - 8:.0f} {oy:.0f} Q {W - right + 20:.0f} '
                 f'{oy - 34:.0f} {px(cent["Massachusetts"][1]):.0f} '
                 f'{py(cent["Massachusetts"][0]):.0f}" fill="none" '
                 f'stroke="var(--color-neutral-700)" stroke-width="9" opacity="0.3"/>')
    ocean_lab = (f'<text x="{ocean_x:.0f}" y="{oy - 14:.0f}" text-anchor="end" '
                 f'class="fm-lab">from across the Atlantic '
                 f'<tspan class="fm-n">{ocean}</tspan></text>')
    total = sum(flows.values())
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} {oy + 56:.0f}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Flow map of ancestral movement across North America. Each dot is a
         colony or state placed at the average of the death coordinates recorded there, and
         each arc is a move from birthplace to place of death, thickness by number of
         people. The heaviest routes are all short and inside New England; a thin set runs
         west to Ohio, the Midwest and Oregon. A separate heavy arc marks {ocean} people who
         arrived across the Atlantic.">
      {ocean_arc}{"".join(arcs)}{"".join(dots)}{"".join(names)}{ocean_lab}
      {legend(pad, oy + 34)}
    </svg>
    <figcaption>Movement inside North America: {total} people whose birthplace and place of
    death are in different colonies or states, on {len(flows)} routes, each arc colored by
    the side of the family that mostly walked it. Dots sit at the mean
    of the coordinates actually recorded in each place, and are sized by how many ancestors
    died there. The thickest line on the map is Massachusetts to Connecticut. Almost every
    heavy route is under two hundred miles — this family moved constantly and hardly went
    anywhere, for six generations, until it did.</figcaption>
  </figure>"""


def atlas_chart(rows, sides):
    """One small map per generation, same projection and extent throughout.

    Holding the frame fixed is the whole point: the cloud of dots does not
    change shape because the map moved, it changes because the family did.
    """
    pts = collections.defaultdict(list)
    for r in rows:
        born, died = lifespan(r)
        if not died or died < 1607 or r["generation"] is None:
            continue
        side = side_of(r["pid"], sides)
        if side and in_america(r["death_lat"], r["death_lon"]):
            pts[r["generation"]].append((r["death_lat"], r["death_lon"], side))

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
    height = rows_n * (ch + lab + gap) + 26

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
        for lat, lon, side in pts[g]:
            cells.append(f'<circle cx="{px(lon):.1f}" cy="{py(lat):.1f}" r="1.9" '
                         f'fill="{SIDE_COLOR.get(side, "var(--color-neutral-500)")}" '
                         f'opacity="0.52"/>')
    span = f"{min(gens)}–{max(gens)}"
    cells.append(legend(0, height - 6))
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
GIVEN_NAME_ARTIFACTS = {"William", "John", "Thomas", "Robert", "Richard", "Henry",
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


ROOT_COUPLE = "PXFK-VML_"          # the record's subject, alone
LAST_COUPLE = "PXFV-YG6_PXFK-QCT"  # the marriage the two sides meet in

SIDES = [("father", "Down the father's side only", "var(--color-accent-700)"),
         ("both", "On both sides", "var(--color-accent-400)"),
         ("mother", "Down the mother's side only", "var(--color-neutral-700)")]

# Three hues that survive being drawn as a half-pixel hairline: a warm brown, a
# near-black, and a light gold between them.
SIDE_COLOR = {"father": "var(--color-accent-700)",
               "both": "var(--color-accent-400)",
               "mother": "var(--color-neutral-900)"}
SIDE_WORD = {"father": "father's side", "both": "both sides", "mother": "mother's side"}


def side_of(pid, sides):
    """father / mother / both / None, for a person id."""
    dad, mom = sides
    in_dad, in_mom = pid in dad, pid in mom
    if in_dad and in_mom:
        return "both"
    if in_dad:
        return "father"
    return "mother" if in_mom else None


def legend(x, y, keys=("father", "both", "mother")):
    out, cx = [], x
    for k in keys:
        out.append(f'<circle cx="{cx:.0f}" cy="{y - 4:.0f}" r="4" fill="{SIDE_COLOR[k]}"/>')
        out.append(f'<text x="{cx + 9:.0f}" y="{y:.0f}" class="lg-t">{SIDE_WORD[k]}</text>')
        cx += 24 + len(SIDE_WORD[k]) * 6.0
    return "".join(out)


def parental_sides():
    """Which half of the tree each ancestor sits in.

    Climbs from each member of the last couple separately. A person can be in
    both sets, and 527 of them are, which is the pedigree collapse the record
    documents elsewhere -- so this returns three answers, not two.
    """
    db = connect(DB)
    db.row_factory = sqlite3.Row
    couples = {r["couple_id"]: dict(r) for r in db.execute("SELECT * FROM fs_couples")}
    up = collections.defaultdict(list)
    for r in db.execute("SELECT * FROM fs_edges"):
        up[r["child_couple_id"]].append((r["parent_couple_id"], r["via"]))
    db.close()

    def climb(starts):
        seen, queue, people = set(starts), collections.deque(starts), set()
        while queue:
            cur = queue.popleft()
            c = couples.get(cur, {})
            for key in ("parent1_pid", "parent2_pid"):
                if c.get(key):
                    people.add(c[key])
            for parent, _ in up.get(cur, []):
                if parent not in seen:
                    seen.add(parent)
                    queue.append(parent)
        return people

    dad = climb([p for p, via in up.get(LAST_COUPLE, []) if via == "parent1"])
    mom = climb([p for p, via in up.get(LAST_COUPLE, []) if via == "parent2"])
    return dad, mom


def surnames_chart(rows, sides):
    """When each family name entered this record and when it left it, by side.

    In a pedigree a surname survives only while sons carry it. The moment the
    descent passes through a daughter the name stops being an ancestor's name,
    which is why almost every bar on this chart ends in a woman.

    Names are grouped by which half of the tree they belong to. The middle group
    is the interesting one: those names occur on both sides, which is the same
    pedigree collapse the record documents elsewhere.
    """
    dad_set, mom_set = sides
    people = collections.defaultdict(list)
    tally = collections.defaultdict(collections.Counter)
    for r in rows:
        # Living people are excluded outright. A dot on this axis is a birth
        # year, and the record does not publish those for the living.
        if "Living" in (r["lifespan"] or ""):
            continue
        s = surname(r["name"])
        born, _ = lifespan(r)
        if not s or not born:
            continue
        people[s].append((born, r["gender"], r["name"], r["generation"]))
        in_dad, in_mom = r["pid"] in dad_set, r["pid"] in mom_set
        if in_dad and in_mom:
            tally[s]["both"] += 1
        elif in_dad:
            tally[s]["father"] += 1
        elif in_mom:
            tally[s]["mother"] += 1

    def side_of(name):
        c = tally[name]
        if c["both"] or (c["father"] and c["mother"]):
            return "both"
        if c["father"]:
            return "father"
        return "mother" if c["mother"] else None

    # Sort on the year alone: generation can be None and would break a plain
    # tuple comparison on ties.
    fams = {s: sorted(v, key=lambda t: t[0]) for s, v in people.items() if len(v) >= 5}
    fams = {s: v for s, v in fams.items() if v[-1][0] >= 1550}
    fams = {s: v for s, v in fams.items() if s not in GIVEN_NAME_ARTIFACTS}
    fams = {s: v for s, v in fams.items() if side_of(s)}

    groups = []
    for key, heading, color in SIDES:
        members = sorted([s for s in fams if side_of(s) == key],
                         key=lambda s: (-fams[s][-1][0], s))
        groups.append((key, heading, color, members[:14], len(members)))

    lo, hi = 1500, 2000
    pad_l, pad_r, top, row_h = 132, 118, 34, 15.5
    span = W - pad_l - pad_r
    slots = sum(len(m) + 2.5 for *_, m, _ in groups)
    height = top + slots * row_h + 34
    x = lambda y: pad_l + span * (min(max(y, lo), hi) - lo) / (hi - lo)

    out, ended_female, shown, i = [], 0, 0, 0.0
    for key, heading, color, members, total in groups:
        out.append(f'<text x="4" y="{top + i * row_h + 4:.1f}" class="sn-head">{heading}'
                   f' <tspan class="sn-headn">{total} names</tspan></text>')
        i += 1.6
        for s in members:
            v = fams[s]
            y = top + i * row_h
            first, last, term = v[0][0], v[-1][0], v[-1][1]
            if term == "FEMALE":
                ended_female += 1
            shown += 1
            out.append(f'<line x1="{x(first):.1f}" y1="{y:.1f}" x2="{x(last):.1f}" '
                       f'y2="{y:.1f}" stroke="{color}" stroke-width="3.4" opacity="0.32" '
                       f'stroke-linecap="round"/>')
            for born, _g, _n, _gen in v:
                out.append(f'<circle cx="{x(born):.1f}" cy="{y:.1f}" r="1.7" '
                           f'fill="{color}" opacity="0.62"/>')
            dot = "var(--color-accent)" if term == "FEMALE" else "var(--color-neutral-800)"
            out.append(f'<circle cx="{x(last):.1f}" cy="{y:.1f}" r="3.5" fill="{dot}"/>')
            out.append(f'<text x="{pad_l - 10}" y="{y + 4:.1f}" text-anchor="end" '
                       f'class="sn-name">{s}</text>')
            out.append(f'<text x="{x(last) + 9:.1f}" y="{y + 4:.1f}" class="sn-end">'
                       f'{"ends in a daughter" if term == "FEMALE" else "record stops"}'
                       f'</text>')
            i += 1
        i += 0.9

    axis_y = top + i * row_h - 4
    axis = "".join(
        f'<text x="{x(t):.1f}" y="{axis_y + 13:.0f}" text-anchor="middle" class="ax">{t}</text>'
        for t in range(1550, 2001, 50))
    counts = {k: n for k, _h, _c, _m, n in groups}
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} {height:.0f}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Family names in three groups: those that occur only on the father's
         side, those on both sides, and those only on the mother's side. Each bar runs from
         the birth year of the earliest ancestor of that name to the latest, and a filled
         dot marks the last person to carry it. Almost every dot marks a woman, because a
         surname stops being an ancestral name as soon as the descent passes through a
         daughter.">
      {"".join(out)}
      <line x1="{pad_l}" y1="{axis_y:.0f}" x2="{W - pad_r}" y2="{axis_y:.0f}"
            stroke="var(--color-divider)" stroke-width="1"/>
      {axis}
    </svg>
    <figcaption>Family names by which half of the tree they belong to:
    <b>{counts['father']}</b> occur only on the father's side, <b>{counts['mother']}</b>
    only on the mother's, and <b>{counts['both']}</b> on both. The fourteen longest-running
    of each are drawn, earliest birth to latest. Small dots are people, the filled dot is
    the last one, and {ended_female} of the {shown} names drawn end in a woman. The middle
    group is the pedigree collapse in another form — those names reach this record twice,
    down each side, and had to be the same family before the two sides ever met.</figcaption>
  </figure>"""


CROSSING_ORDER = [
    ("I · The Great Migration", "England, Wales & Scotland", ("England", "Wales", "Scotland")),
    ("II · New Netherland", "the Dutch Republic", ("Netherlands",)),
    ("III · The Palatines", "the Rhineland", ("Germany",)),
    ("IV · The Ulster Scots", "Ulster & Ireland", ("Ulster", "Ireland")),
    ("V · The Industrial Crossing", "born from 1800", ()),
]


def crossings_by_side(rows, sides):
    """Which side of the family each of the five crossings arrived on.

    Diverging from a center line: the father's side left, the mother's right,
    and the people who are ancestors on both sides in the middle. The Palatine
    row is the one to read -- it has no left-hand bar at all.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("gc", os.path.join(HERE, "generate-charts.py"))
    gc = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ["x"]
    try:
        spec.loader.exec_module(gc)
    except SystemExit:
        pass
    finally:
        sys.argv = argv

    tally = collections.defaultdict(collections.Counter)
    for r in rows:
        nation = gc.nation_of(r["birth_place"])
        if not nation or not gc.in_america(r["death_place"]):
            continue
        born, died = lifespan(r)
        if (died or 9999) < 1607 or (born or 9999) < 1500:
            continue
        if (born or 0) >= 1800:
            key = "V · The Industrial Crossing"
        else:
            key = next((k for k, _sub, nations in CROSSING_ORDER if nation in nations), None)
        side = side_of(r["pid"], sides)
        if key and side:
            tally[key][side] += 1

    peak = max((t["father"] + t["both"] + t["mother"]) for t in tally.values()) or 1
    unit = 300 / peak
    mid, top, row_h = W / 2 + 40, 74, 74
    height = top + len(CROSSING_ORDER) * row_h + 40
    out = [f'<line x1="{mid}" y1="{top - 26}" x2="{mid}" y2="{height - 46}" '
           f'stroke="var(--color-divider)" stroke-width="1"/>',
           f'<text x="{mid - 12}" y="{top - 34}" text-anchor="end" class="cs-ax">'
           f"father&#8217;s side</text>",
           f'<text x="{mid + 12}" y="{top - 34}" class="cs-ax">mother&#8217;s side</text>']

    for i, (key, sub_label, _n) in enumerate(CROSSING_ORDER):
        t = tally[key]
        y = top + i * row_h
        out.append(f'<text x="26" y="{y + 4:.0f}" class="cs-name">{key}</text>')
        out.append(f'<text x="26" y="{y + 21:.0f}" class="cs-sub">{sub_label}</text>')
        bh = 21
        fw, mw, bw = t["father"] * unit, t["mother"] * unit, t["both"] * unit
        out.append(f'<rect x="{mid - fw - bw / 2:.1f}" y="{y - bh / 2 + 4:.0f}" '
                   f'width="{max(fw, 0.8):.1f}" height="{bh}" fill="{SIDE_COLOR["father"]}" '
                   f'opacity="0.82"/>')
        if t["both"]:
            out.append(f'<rect x="{mid - bw / 2:.1f}" y="{y - bh / 2 + 4:.0f}" '
                       f'width="{bw:.1f}" height="{bh}" fill="{SIDE_COLOR["both"]}" '
                       f'opacity="0.9"/>')
        out.append(f'<rect x="{mid + bw / 2:.1f}" y="{y - bh / 2 + 4:.0f}" '
                   f'width="{max(mw, 0.8):.1f}" height="{bh}" fill="{SIDE_COLOR["mother"]}" '
                   f'opacity="0.82"/>')
        out.append(f'<text x="{mid - fw - bw / 2 - 9:.1f}" y="{y + 9:.0f}" text-anchor="end" '
                   f'class="cs-n">{t["father"]}</text>')
        out.append(f'<text x="{mid + bw / 2 + mw + 9:.1f}" y="{y + 9:.0f}" class="cs-n">'
                   f'{t["mother"]}</text>')
        if t["both"]:
            out.append(f'<text x="{mid:.0f}" y="{y + 34:.0f}" text-anchor="middle" '
                       f'class="cs-both">{t["both"]} on both</text>')

    pal = tally["III · The Palatines"]
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} {height:.0f}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Diverging bar chart of the five crossings. Bars extend left for
         ancestors on the father's side and right for the mother's. The Great Migration
         extends much further left than right. New Netherland and the Palatines extend only
         to the right, and the Palatine row has no left-hand bar at all: none of those
         ancestors are on the father's side.">
      {"".join(out)}
      {legend(26, height - 12, keys=("father", "both", "mother"))}
    </svg>
    <figcaption>Each crossing, by the side of the family it arrived on. The English came
    down the father's side three to one. <b>The Palatines came down the mother's side and
    nothing else</b> — {pal["mother"]} people, none of them on the father's side — and the
    Dutch are nearly as lopsided. These two families did not just arrive in different
    decades. They arrived from different countries, and only met in the 1970s.</figcaption>
  </figure>"""


AMERICA = ("United States", "Colonial America", "Massachusetts", "Connecticut",
           "Rhode Island", "New Hampshire", "Vermont", "Maine", "New York", "New Jersey",
           "Pennsylvania", "Virginia", "Maryland", "Ohio", "Plymouth Colony", "Canada",
           "British North America", "New Netherland", "Delaware", "Carolina", "Georgia")

ULSTER_COUNTIES = ("Antrim", "Down", "Derry", "Londonderry", "Donegal", "Tyrone",
                   "Armagh", "Fermanagh", "Ulster")

# Ireland-born ancestors carrying one of these names are grouped with Scotland.
# Every Irish family in this record is an Ulster Scots one -- Lowland Presbyterians
# planted in the north of Ireland in the 1600s, who then crossed again -- and the
# surnames are Lowland Scots throughout. This is an interpretive call and the page
# says so; the rule is here rather than buried so it can be argued with.
ULSTER_SCOTS_NAMES = {
    "Campbell", "Gilmore", "Gilmour", "Borland", "Boreland", "Ross", "Linton",
    "Culbertson", "Gibson", "Jamison", "Jameson", "Mitchell", "Clark", "Clarke",
    "Faulkner", "Gartley", "Barkley", "Templeton", "Wilson", "Craig", "Hamilton",
    "Kerr", "Maxwell", "Sloan", "Rankin", "Blair", "Boyd", "Smith",
}

ORIGIN_GROUPS = [
    ("England & Wales", ("England", "Wales", "Cornwall")),
    ("Germany & the Palatinate", ("Germany", "Pfalz", "Palatin", "Hesse", "Baden",
                                  "Wurttemberg", "Rhineland", "Prussia", "Bavaria", "Saxony")),
    ("Netherlands", ("Netherlands", "Holland", "Utrecht", "Zeeland", "Gelderland")),
    ("France", ("France", "Normandy", "Perche", "Rouen")),
    ("Switzerland", ("Switzerland", "Swiss")),
    ("Scandinavia", ("Sweden", "Norway", "Denmark", "Finland")),
    ("Belgium & Walloon", ("Belgium", "Hainaut", "Walloon", "Wallon")),
]


def born_in_america(place):
    return bool(place) and any(k in place for k in AMERICA)


def origin_group(person):
    """Where a crossing ancestor came from, grouped by people rather than borders.

    Scotland and Ulster are one band. The Ulster families in this record are
    Lowland Scots planted in Ireland in the 1600s -- the page argues this at
    length -- so splitting them from Scotland by a coastline would separate one
    population into two. Ireland-born ancestors whose surname is not on the
    Ulster Scots list stay separate.
    """
    place = person.get("birth_place") or ""
    surname_last = (person.get("name") or "").split()[-1] if person.get("name") else ""
    if "Scotland" in place or any(k in place for k in ULSTER_COUNTIES):
        return "Scotland & Ulster"
    if "Ireland" in place:
        return ("Scotland & Ulster" if surname_last in ULSTER_SCOTS_NAMES
                else "Ireland, other")
    return next((n for n, keys in ORIGIN_GROUPS if any(k in place for k in keys)),
                "origin abroad, unidentified")


def ancestry_weights(people):
    """Expected share of autosomal DNA, partitioned so it adds to exactly 100%.

    Each parent contributes half of what their child contributes, and a person
    reached by several lines gets the sum of all of them. Two rules make the
    total come out at one rather than somewhere above it:

      * a line stops being followed once it leaves America, so the ancestors of
        an immigrant are not counted again on top of the immigrant;
      * where a couple records only one parent, the missing half is booked as a
        gap rather than quietly evaporating.

    Returns share and headcount by origin, where the American lines stop, and
    the single-parent gap.
    """
    db = connect(DB)
    db.row_factory = sqlite3.Row
    couples = {r["couple_id"]: dict(r) for r in db.execute("SELECT * FROM fs_couples")}
    up = collections.defaultdict(list)
    for r in db.execute("SELECT * FROM fs_edges"):
        if r["parent_couple_id"] in couples and r["child_couple_id"] in couples:
            up[r["child_couple_id"]].append((r["parent_couple_id"], r["via"]))
    db.close()

    by_pid = {p["pid"]: p for p in people}

    def abroad(pid):
        place = by_pid.get(pid, {}).get("birth_place")
        return bool(place) and not born_in_america(place)

    seen, order, stack = set(), [], [(ROOT_COUPLE, False)]
    while stack:
        node, done = stack.pop()
        if done:
            order.append(node)
            continue
        if node in seen:
            continue
        seen.add(node)
        stack.append((node, True))
        for parent, _ in up.get(node, []):
            stack.append((parent, False))
    order.reverse()

    weight = collections.defaultdict(float)
    weight[couples[ROOT_COUPLE]["parent1_pid"]] = 1.0
    gap, passes_up = 0.0, set()
    for cid in order:
        c = couples[cid]
        for parent_id, via in up.get(cid, []):
            heir = c["parent1_pid"] if via == "parent1" else c["parent2_pid"]
            if not heir or abroad(heir):
                continue                       # the ocean absorbs the line
            passes_up.add(heir)
            share = weight[heir] / 2.0
            pc, got = couples[parent_id], 0
            for key in ("parent1_pid", "parent2_pid"):
                if pc.get(key):
                    weight[pc[key]] += share
                    got += 1
            if got == 1:
                gap += share                   # the other parent was never entered

    share_by, count_by, stops = collections.Counter(), collections.Counter(), collections.Counter()
    for pid, v in weight.items():
        if v <= 1e-12:
            continue
        if abroad(pid):
            g = origin_group(by_pid.get(pid, {}))
            share_by[g] += v
            count_by[g] += 1
        elif pid not in passes_up:
            p = by_pid.get(pid, {})
            blob = f"{p.get('birth_place') or ''} {p.get('death_place') or ''}"
            where = next((x for x in ("Pennsylvania", "New York", "Ohio", "Massachusetts",
                                      "Connecticut", "Vermont", "Rhode Island", "New Jersey",
                                      "Virginia", "New Hampshire", "Maine", "Iowa", "Illinois")
                          if x in blob), "place unrecorded")
            stops[where] += v
    return share_by, count_by, stops, gap


def ancestry_chart(rows, sides):
    """Headcount of immigrants against expected share of DNA.

    A slopegraph because the point is the reordering. Counting immigrants and
    counting inheritance give almost opposite answers, and the lines cross.
    """
    raw, count, stops, gap = ancestry_weights(rows)
    traced = sum(raw.values())
    lost = sum(stops.values()) + gap
    # Composition is a share of what the record can place, not of the whole
    # pedigree. Mixing the two would put "stops in Pennsylvania" on the same
    # axis as "England", and an absence of evidence is not an ancestry.
    share = collections.Counter({k: v / traced for k, v in raw.items()})
    tot_n = sum(count.values()) or 1

    names = [n for n in set(list(count) + list(share)) if count.get(n) or share.get(n)]
    names.sort(key=lambda n: -share.get(n, 0.0))

    pad_l, pad_r, top, h = 250, 250, 96, 430
    x1, x2 = pad_l, W - pad_r
    lmax = max(count.values()) / tot_n
    rmax = max(share.values())

    def ly(n):
        return top + h * (1 - (count.get(n, 0) / tot_n) / lmax)

    def ry(n):
        return top + h * (1 - share.get(n, 0.0) / rmax)

    out = [f'<text x="{x1}" y="{top - 44}" text-anchor="end" class="an-hd">share of the '
           f'{tot_n} immigrants</text>',
           f'<text x="{x2}" y="{top - 44}" class="an-hd">share of the DNA</text>',
           f'<line x1="{x1}" y1="{top - 24}" x2="{x1}" y2="{top + h + 10}" '
           f'stroke="var(--color-divider)"/>',
           f'<line x1="{x2}" y1="{top - 24}" x2="{x2}" y2="{top + h + 10}" '
           f'stroke="var(--color-divider)"/>']

    # de-overlap the labels on each side
    def stack(fn):
        pts = sorted(((fn(n), n) for n in names))
        out2, prev = [], None
        for y, n in pts:
            yy = y if prev is None else max(y, prev + 17)
            out2.append((n, y, yy)); prev = yy
        return {n: (y, yy) for n, y, yy in out2}
    L, R = stack(ly), stack(ry)

    for n in names:
        c, s = count.get(n, 0) / tot_n, share.get(n, 0.0)
        rise = s > c
        colour = "var(--color-accent-700)" if rise else "var(--color-neutral-700)"
        out.append(f'<path d="M {x1} {L[n][0]:.1f} C {x1 + 120} {L[n][0]:.1f}, '
                   f'{x2 - 120} {R[n][0]:.1f}, {x2} {R[n][0]:.1f}" fill="none" '
                   f'stroke="{colour}" stroke-width="{1 + 9 * s:.2f}" opacity="0.45"/>')
        out.append(f'<circle cx="{x1}" cy="{L[n][0]:.1f}" r="3.5" fill="{colour}"/>')
        out.append(f'<circle cx="{x2}" cy="{R[n][0]:.1f}" r="3.5" fill="{colour}"/>')
        out.append(f'<text x="{x1 - 12}" y="{L[n][1] + 4:.1f}" text-anchor="end" '
                   f'class="an-lab">{n} <tspan class="an-n">{count.get(n,0)}</tspan> '
                   f'<tspan class="an-pc">{100*c:.0f}%</tspan></text>')
        out.append(f'<text x="{x2 + 12}" y="{R[n][1] + 4:.1f}" class="an-lab">'
                   f'<tspan class="an-pc">{100*s:.1f}%</tspan> {n}</text>')

    fy = top + h + 46
    out.append(f'<text x="{W/2:.0f}" y="{fy}" text-anchor="middle" class="an-foot">'
               f'shares of the {100*traced:.0f}% of this pedigree that reaches a known '
               f'origin &#183; the other {100*lost:.0f}% stops before a coast</text>')
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} {fy + 26:.0f}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Slopegraph comparing each origin's share of immigrant ancestors on the
         left with its expected share of inherited DNA on the right. England falls from
         about 85 per cent of the immigrants to about a third of the DNA, while Ulster and
         Ireland rise from 4 per cent to 22 and Scotland from 1.5 per cent to 13. The lines
         cross.">
      {"".join(out)}
    </svg>
    <figcaption>Left: each origin's share of the {tot_n} ancestors who crossed an ocean.
    Right: its share of the inherited DNA, since an ancestor {chr(110)} generations back
    contributes 1/2<tspan></tspan>&#8319; of it. Both columns are shares of what this record
    can actually place — {100*traced:.0f}% of the pedigree; the missing {100*lost:.0f}% is
    counted separately below rather than mixed in here. The lines cross because the English
    arrived in the sixteen-hundreds and the Scots and Irish in the eighteen-hundreds, and
    eight generations of halving is a factor of 256.</figcaption>
  </figure>"""


NEW_ENGLAND = ("Massachusetts", "Connecticut", "New Hampshire", "Vermont",
               "Rhode Island", "Maine")
ULSTER_SURNAMES_US = {"Leard", "Gartley", "Campbell", "Gilmore", "Borland", "Boreland",
                      "Ross", "Culbertson", "Gibson", "Jamison", "Mitchell", "Barkley",
                      "Templeton", "Craig", "Blair", "Boyd", "Owen"}


def classify_gap(person):
    """A probable origin for a line that stops in America, or None.

    Inference, not evidence, and labeled that way wherever it is shown. A
    colonial New England birth before 1800 is Great Migration stock in almost
    every case; a Pennsylvania line carrying an Ulster surname is Ulster Scots;
    a Mohawk Valley line is Palatine. Everything else stays unclear rather than
    being pushed into whichever bucket flatters the argument.
    """
    blob = f"{person.get('birth_place') or ''} {person.get('death_place') or ''}"
    surname_last = (person.get("name") or "").split()[-1] if person.get("name") else ""
    years = re.findall(r"\b(1[5-9]\d\d)\b", person.get("lifespan") or "")
    born = int(years[0]) if years else None
    if "Pennsylvania" in blob and surname_last in ULSTER_SURNAMES_US:
        return "Scotland & Ulster", "Pennsylvania, Ulster surname"
    if any(k in blob for k in ("Mohawk", "Montgomery, New York", "Herkimer", "Palatine")):
        return "Germany & the Palatinate", "Mohawk Valley"
    if any(k in blob for k in NEW_ENGLAND) and (born or 9999) < 1800:
        return "England & Wales", "colonial New England"
    if not blob.strip():
        return None, "no place recorded at all"
    return None, "origin unclear"


def gap_breakdown(rows):
    """Where the unplaced ancestry sits, and what can be inferred about it."""
    _share, _count, stops, gap = ancestry_weights(rows)
    by = {p["pid"]: p for p in rows}
    db = connect(DB)
    db.row_factory = sqlite3.Row
    couples = {r["couple_id"]: dict(r) for r in db.execute("SELECT * FROM fs_couples")}
    up = collections.defaultdict(list)
    for r in db.execute("SELECT * FROM fs_edges"):
        if r["parent_couple_id"] in couples and r["child_couple_id"] in couples:
            up[r["child_couple_id"]].append((r["parent_couple_id"], r["via"]))
    db.close()

    def abroad(pid):
        pl = by.get(pid, {}).get("birth_place")
        return bool(pl) and not born_in_america(pl)

    seen, order, stack = set(), [], [(ROOT_COUPLE, False)]
    while stack:
        node, done = stack.pop()
        if done:
            order.append(node); continue
        if node in seen:
            continue
        seen.add(node); stack.append((node, True))
        for p, _ in up.get(node, []):
            stack.append((p, False))
    order.reverse()
    weight = collections.defaultdict(float)
    weight[couples[ROOT_COUPLE]["parent1_pid"]] = 1.0
    passes = set()
    for cid in order:
        c = couples[cid]
        for pid_c, via in up.get(cid, []):
            heir = c["parent1_pid"] if via == "parent1" else c["parent2_pid"]
            if not heir or abroad(heir):
                continue
            passes.add(heir)
            share = weight[heir] / 2.0
            pc = couples[pid_c]
            for k in ("parent1_pid", "parent2_pid"):
                if pc.get(k):
                    weight[pc[k]] += share

    probable, unclear = collections.Counter(), collections.Counter()
    for pid, v in weight.items():
        if v <= 1e-12 or abroad(pid) or pid in passes:
            continue
        origin, why = classify_gap(by.get(pid, {}))
        if origin:
            probable[origin] += v
        else:
            unclear[why] += v
    unclear["one parent never recorded"] += gap
    return probable, unclear


def coverage_chart(rows, sides):
    """Waterfall: the pedigree reduced to what can be placed, by origin not by state.

    The steps that come off are labeled by what the missing ancestry probably
    was, because 'stops in Pennsylvania' is not an origin -- it is the place a
    paper trail ended, and putting a state on the same axis as a country was
    the conflation this figure exists to undo.
    """
    share, _count, _stops, _gap = ancestry_weights(rows)
    traced = sum(share.values())
    probable, unclear = gap_breakdown(rows)

    steps = [(f"probably {k}", v, "prob") for k, v in probable.most_common()]
    steps += [(k, v, "unk") for k, v in unclear.most_common()]

    pad_l, pad_r, top, h = 30, 30, 104, 286
    n = len(steps) + 2
    span = W - pad_l - pad_r
    gapx = span / n
    bw = gapx * 0.6
    y0 = top + h
    out, x, running = [], pad_l + gapx * 0.2, 1.0

    def bar(x, ytop, ht, fill, op):
        return (f'<rect x="{x:.1f}" y="{ytop:.1f}" width="{bw:.1f}" '
                f'height="{max(ht,1.2):.1f}" fill="{fill}" opacity="{op}" rx="1.5"/>')

    def cap(x, y, txt, cls):
        return (f'<text x="{x + bw/2:.1f}" y="{y:.1f}" text-anchor="middle" '
                f'class="{cls}">{txt}</text>')

    out.append(bar(x, y0 - h, h, "var(--color-neutral-700)", "0.5"))
    out.append(cap(x, y0 - h - 10, "100%", "wf-num"))
    out.append(cap(x, y0 + 18, "the whole", "wf-lab"))
    out.append(cap(x, y0 + 31, "pedigree", "wf-lab"))
    x += gapx

    for name, v, kind in steps:
        htop = y0 - running * h
        running -= v
        colour = ("var(--color-accent-500)" if kind == "prob"
                  else "var(--color-neutral-500)")
        out.append(bar(x, htop, v * h, colour, "0.55" if kind == "prob" else "0.35"))
        out.append(f'<line x1="{x - gapx + bw:.1f}" y1="{htop:.1f}" x2="{x:.1f}" '
                   f'y2="{htop:.1f}" stroke="var(--color-neutral-400)" stroke-width="0.8" '
                   f'stroke-dasharray="2 2"/>')
        out.append(cap(x, htop - 8, f"&#8722;{v*100:.1f}%", "wf-num"))
        words, lines, cur = name.split(), [], ""
        for wd in words:
            if len(cur) + len(wd) > 15:
                lines.append(cur); cur = wd
            else:
                cur = (cur + " " + wd).strip()
        lines.append(cur)
        for i, ln in enumerate(lines[:3]):
            out.append(cap(x, y0 + 18 + i * 13, ln, "wf-lab"))
        x += gapx

    out.append(bar(x, y0 - running * h, running * h, "var(--color-accent-800)", "0.9"))
    out.append(cap(x, y0 - running * h - 10, f"{running*100:.0f}%", "wf-num"))
    out.append(cap(x, y0 + 18, "traced to a", "wf-lab"))
    out.append(cap(x, y0 + 31, "known origin", "wf-lab"))
    out.append(f'<line x1="{pad_l}" y1="{y0:.1f}" x2="{W-pad_r}" y2="{y0:.1f}" '
               f'stroke="var(--color-divider)"/>')
    out.append(f'<rect x="{pad_l}" y="{top-46}" width="13" height="13" rx="2" '
               f'fill="var(--color-accent-500)" opacity="0.55"/>')
    out.append(f'<text x="{pad_l+20}" y="{top-35}" class="wf-key">a probable origin, from '
               f'place and surname &#8212; inference, not evidence</text>')
    out.append(f'<rect x="{pad_l+352}" y="{top-46}" width="13" height="13" rx="2" '
               f'fill="var(--color-neutral-500)" opacity="0.35"/>')
    out.append(f'<text x="{pad_l+372}" y="{top-35}" class="wf-key">no usable inference</text>')
    prob_total = sum(probable.values())
    H = y0 + 72
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} {H:.0f}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Waterfall from the whole pedigree down to the {traced*100:.0f} per cent
         traced to a known origin. The steps removed are labeled by what the missing
         ancestry probably was rather than by the American state the record stops in: about
         {prob_total*100:.0f} per cent can be given a probable origin from place and surname,
         and the rest cannot.">
      {"".join(out)}
    </svg>
    <figcaption>How much of the pedigree can be placed, and what the rest probably was. Each
    step is labeled by likely origin rather than by the state the trail ends in, because a
    state is not an origin. <b>{traced*100:.0f}% reaches a documented crossing</b>; another
    <b>{prob_total*100:.0f}% has a probable one</b> from place and surname together; the
    remainder has neither. Only the final bar is described by the next figure.</figcaption>
  </figure>"""


def composition_chart(rows, sides):
    """The placeable ancestry, as a share of itself."""
    raw, count, _stops, _gap = ancestry_weights(rows)
    traced = sum(raw.values())
    parts = [(k, v / traced, count[k]) for k, v in raw.most_common()]
    keep = [p for p in parts if p[1] >= 0.02]
    small = sum(p[1] for p in parts if p[1] < 0.02)
    smalln = sum(p[2] for p in parts if p[1] < 0.02)
    if small:
        folded = [p[0] for p in parts if p[1] < 0.02]
        folded = [f.split(" &")[0].split(",")[0] for f in folded]
        label = ", ".join(folded[:-1]) + " and " + folded[-1] if len(folded) > 1 else folded[0]
        keep.append((label, small, smalln))

    cx, cy, r, rin = 300, 250, 165, 92
    COLS = ["var(--color-accent-700)", "var(--color-neutral-800)", "var(--color-accent-400)",
            "var(--color-accent-600)", "var(--color-neutral-500)", "var(--color-neutral-400)"]
    out, ang = [], -math.pi / 2
    for i, (name, frac, n) in enumerate(keep):
        sweep = frac * 2 * math.pi
        a2 = ang + sweep
        big = 1 if sweep > math.pi else 0
        x1, y1 = cx + r * math.cos(ang), cy + r * math.sin(ang)
        x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
        xi, yi = cx + rin * math.cos(a2), cy + rin * math.sin(a2)
        xj, yj = cx + rin * math.cos(ang), cy + rin * math.sin(ang)
        out.append(f'<path d="M {x1:.1f} {y1:.1f} A {r} {r} 0 {big} 1 {x2:.1f} {y2:.1f} '
                   f'L {xi:.1f} {yi:.1f} A {rin} {rin} 0 {big} 0 {xj:.1f} {yj:.1f} Z" '
                   f'fill="{COLS[i % len(COLS)]}" opacity="0.88"/>')
        ang = a2
    # legend, because labelling slices of two per cent inside a donut is unreadable
    ly = 108
    for i, (name, frac, n) in enumerate(keep):
        out.append(f'<rect x="{cx + 250}" y="{ly - 10}" width="13" height="13" rx="2" '
                   f'fill="{COLS[i % len(COLS)]}" opacity="0.88"/>')
        out.append(f'<text x="{cx + 271}" y="{ly}" class="pi-lab">{name}</text>')
        out.append(f'<text x="{cx + 271}" y="{ly + 16}" class="pi-sub">'
                   f'<tspan class="pi-pc">{frac*100:.1f}%</tspan> &#183; {n} '
                   f'{"crossing" if n == 1 else "crossings"}</text>')
        ly += 46
    out.append(f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" class="pi-mid">'
               f'{traced*100:.0f}%</text>')
    out.append(f'<text x="{cx}" y="{cy + 15}" text-anchor="middle" class="pi-midsub">'
               f'of the pedigree</text>')
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} 500" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Donut chart of the placeable ancestry. England and Wales is 47 per cent
         and Scotland and Ulster 45 per cent, between them nine tenths of it; Ireland other,
         Germany, the Netherlands and a remainder make up the rest.">
      {"".join(out)}
    </svg>
    <figcaption>The second question: of the {traced*100:.0f}% that can be placed, where it
    came from. Two origins are nine-tenths of it and they are almost level — and one of them
    got there with 305 people and the other with 14.</figcaption>
  </figure>"""


FULL_DATE = re.compile(r"^\s*\d{1,2}\s+[A-Z][a-z]+\s+\d{3,4}\s*$")
VAGUE_DATE = re.compile(r"\b(about|abt|circa|c\.|bef|aft|before|after|estimated|calculated)\b",
                        re.I)


def clean_age(row):
    """Age at death, but only where the dates can carry the weight.

    Both ends must be a full day-month-year with no hedging word attached.
    Year-only records are where the rounding lives: across the whole tree 25.8%
    of ages land on a multiple of five against a chance 20%, and inside this
    filter it falls to chance. The filter is not tidiness -- it is the
    difference between a recorded age and a remembered one.
    """
    birth = (row.get("birth_date") or "").strip()
    death = (row.get("death_date") or "").strip()
    if VAGUE_DATE.search(birth) or VAGUE_DATE.search(death):
        return None
    if not FULL_DATE.match(birth) or not FULL_DATE.match(death):
        return None
    born, died = lifespan(row)
    if not born or not died or died < born:
        return None
    return died - born


def lifespan_chart(rows, sides):
    """Age at death by side of the family and by sex, as decile strips.

    The headline is that there is almost nothing to see, and the reason there is
    almost nothing to see is the interesting part: everyone in a pedigree
    survived to have children, so the distribution has had its left tail removed
    before the chart starts.
    """
    dad, mom = sides
    groups = collections.defaultdict(list)
    for r in rows:
        if "Living" in (r["lifespan"] or ""):
            continue
        age = clean_age(r)
        if age is None:
            continue
        in_d, in_m = r["pid"] in dad, r["pid"] in mom
        side = ("father's side" if in_d and not in_m
                else "mother's side" if in_m and not in_d else None)
        if side is None or r.get("gender") not in ("MALE", "FEMALE"):
            continue
        groups[(side, "men" if r["gender"] == "MALE" else "women")].append(age)

    keys = [(s, g) for s in ("father's side", "mother's side") for g in ("men", "women")]
    keys = [k for k in keys if len(groups.get(k, [])) >= 60]
    lo, hi = 15, 105
    pad_l, pad_r, top, row_h = 190, 120, 96, 74
    span = W - pad_l - pad_r
    x = lambda a: pad_l + span * (min(max(a, lo), hi) - lo) / (hi - lo)
    height = top + len(keys) * row_h + 76

    def dec(v):
        v = sorted(v)
        return [v[min(int(len(v) * i / 10), len(v) - 1)] for i in range(1, 10)]

    out = []
    for t in range(20, 106, 10):
        out.append(f'<line x1="{x(t):.1f}" y1="{top-26}" x2="{x(t):.1f}" '
                   f'y2="{top + len(keys)*row_h - 20:.1f}" stroke="var(--color-divider)" '
                   f'stroke-width="{1 if t % 20 == 0 else 0.5}" opacity="0.7"/>')
        out.append(f'<text x="{x(t):.1f}" y="{top-34}" text-anchor="middle" class="ax">{t}</text>')

    for i, k in enumerate(keys):
        v = groups[k]
        d = dec(v)
        y = top + i * row_h
        colour = ("var(--color-accent-700)" if k[0].startswith("father")
                  else "var(--color-neutral-800)")
        out.append(f'<rect x="{x(d[0]):.1f}" y="{y:.1f}" width="{x(d[8])-x(d[0]):.1f}" '
                   f'height="20" rx="3" fill="{colour}" opacity="0.14"/>')
        out.append(f'<rect x="{x(d[2]):.1f}" y="{y:.1f}" width="{x(d[6])-x(d[2]):.1f}" '
                   f'height="20" rx="3" fill="{colour}" opacity="0.3"/>')
        out.append(f'<rect x="{x(d[3]):.1f}" y="{y:.1f}" width="{x(d[5])-x(d[3]):.1f}" '
                   f'height="20" rx="2" fill="{colour}" opacity="0.45"/>')
        med = statistics.median(v)
        out.append(f'<line x1="{x(med):.1f}" y1="{y-4:.0f}" x2="{x(med):.1f}" '
                   f'y2="{y+24:.0f}" stroke="{colour}" stroke-width="2.4"/>')
        mean = statistics.mean(v)
        out.append(f'<circle cx="{x(mean):.1f}" cy="{y+10:.0f}" r="3.4" fill="none" '
                   f'stroke="{colour}" stroke-width="1.6"/>')
        out.append(f'<text x="{pad_l-16}" y="{y+8:.0f}" text-anchor="end" class="ls-lab">'
                   f'{k[0]} &#183; {k[1]}</text>')
        out.append(f'<text x="{pad_l-16}" y="{y+22:.0f}" text-anchor="end" class="ls-sub">'
                   f'{len(v):,} people</text>')
        out.append(f'<text x="{W-pad_r+14}" y="{y+8:.0f}" class="ls-sub">median '
                   f'<tspan class="ls-n">{med:.0f}</tspan></text>')
        out.append(f'<text x="{W-pad_r+14}" y="{y+22:.0f}" class="ls-sub">mean '
                   f'<tspan class="ls-n">{mean:.1f}</tspan></text>')

    ky = top + len(keys) * row_h + 6
    out.append(f'<rect x="{pad_l}" y="{ky}" width="26" height="11" rx="2" '
               f'fill="var(--color-neutral-800)" opacity="0.14"/>')
    out.append(f'<text x="{pad_l+33}" y="{ky+10}" class="ls-sub">10th&#8211;90th percentile</text>')
    out.append(f'<rect x="{pad_l+180}" y="{ky}" width="26" height="11" rx="2" '
               f'fill="var(--color-neutral-800)" opacity="0.45"/>')
    out.append(f'<text x="{pad_l+213}" y="{ky+10}" class="ls-sub">40th&#8211;60th</text>')
    out.append(f'<line x1="{pad_l+310}" y1="{ky-2}" x2="{pad_l+310}" y2="{ky+13}" '
               f'stroke="var(--color-neutral-800)" stroke-width="2.4"/>')
    out.append(f'<text x="{pad_l+318}" y="{ky+10}" class="ls-sub">median</text>')
    out.append(f'<circle cx="{pad_l+392}" cy="{ky+5}" r="3.4" fill="none" '
               f'stroke="var(--color-neutral-800)" stroke-width="1.6"/>')
    out.append(f'<text x="{pad_l+402}" y="{ky+10}" class="ls-sub">mean</text>')
    out.append(f'<text x="{W/2:.0f}" y="{height-16}" text-anchor="middle" class="ls-sub">'
               f'age at death, in years</text>')

    allv = [a for k in keys for a in groups[k]]
    heap = 100 * sum(1 for a in allv if a % 5 == 0) / len(allv)
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} {height:.0f}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Decile strips of age at death for four groups: men and women on the
         father's side and on the mother's side. All four distributions are nearly identical,
         with medians of 59 to 60 and the middle fifth of each falling between about 54 and
         65.">
      {"".join(out)}
    </svg>
    <figcaption>Age at death for the {len(allv)} people whose birth and death are both given
    as a full day, month and year with no hedging word attached — the only ones whose age can
    be trusted to a year. The pale band is the tenth to ninetieth percentile, the darker one
    the middle fifth, the rule the median and the ring the mean. <b>All four distributions
    are effectively the same.</b> {heap:.0f}% of these ages land on a multiple of five
    against a chance expectation of 20%, so unlike the wider record this cohort is not
    rounded.</figcaption>
  </figure>"""


CHARTS = {"lives": lives_chart, "occupancy": occupancy_chart, "flow": flow_map,
          "lifespan": lifespan_chart,
          "atlas": atlas_chart, "surnames": surnames_chart,
          "crossings_side": crossings_by_side, "ancestry": ancestry_chart,
          "coverage": coverage_chart, "composition": composition_chart}


def main():
    rows = load()
    sides = parental_sides()
    page = open(PAGE, encoding="utf-8").read()
    written = []
    for name, fn in CHARTS.items():
        begin, end = f"<!-- ATLAS:{name} -->", f"<!-- /ATLAS:{name} -->"
        if begin not in page:
            print(f"  (no marker for {name}, skipped)")
            continue
        block = fn(rows, sides)
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
