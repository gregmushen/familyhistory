#!/usr/bin/env python3
"""Generate the two data figures for the record, as inline SVG.

  1. A streamgraph of where each generation died — the family flowing west.
  2. A timeline of the five crossings, on a common year axis.

Both read live from the FamilySearch mirror, so re-running after hydration
finishes updates them. Output is written between HTML markers in index.html:

    <!-- CHART:stream -->  …generated…  <!-- /CHART:stream -->
    <!-- CHART:crossings -->  …generated…  <!-- /CHART:crossings -->

No JavaScript, no chart library — the page has neither and should keep neither.
Colours come from the design-system tokens, not hex.
"""
import collections
import os
import re
import sqlite3
import sys

DB = os.path.expanduser("~/.local/share/familysearch-pp-cli/data.db")
ROOT_COUPLE = "PXFK-VML_"
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

REGIONS = [
    ("New England", "var(--color-neutral-800)",
     ["Massachusetts", "Plymouth", "Connecticut", "Rhode Island",
      "New Hampshire", "Vermont", "Maine"]),
    ("Mid-Atlantic", "var(--color-neutral-500)",
     ["New York", "New Jersey", "Pennsylvania", "Maryland", "Delaware",
      "New Netherland"]),
    ("Midwest", "var(--color-accent-600)",
     ["Ohio", "Indiana", "Illinois", "Iowa", "Michigan", "Wisconsin",
      "Missouri", "Kansas", "Nebraska", "Minnesota"]),
    ("West", "var(--color-accent-300)",
     ["Oregon", "California", "Washington", "Nevada", "Idaho", "Colorado", "Utah"]),
]

# The five crossings: label, span, and how to count its people.
CROSSINGS = [
    ("I", "The Great Migration", 1620, 1640, "england"),
    ("II", "New Netherland", 1624, 1664, "dutch"),
    ("III", "The Palatines", 1709, 1760, "german"),
    ("IV", "The Ulster Scots", 1718, 1775, "ulster"),
    ("V", "The Industrial Crossing", 1840, 1870, "late"),
]


def region_of(place):
    for name, _, towns in REGIONS:
        for t in towns:
            if t in place:
                return name


def nation_of(p):
    if not p:
        return None
    q = p.lower()
    if "northern ireland" in q or any(u in q for u in (
            "antrim", "down", "armagh", "londonderry", "derry", "fermanagh",
            "tyrone", "donegal", "monaghan", "ulster")):
        return "Ulster"
    if "ireland" in q:
        return "Ireland"
    if "scotland" in q:
        return "Scotland"
    if "wales" in q or "caernarfon" in q or "glamorgan" in q or "monmouth" in q:
        return "Wales"
    if "england" in q or "united kingdom" in q:
        return "England"
    if any(x in q for x in ("germany", "baden", "bavaria", "prussia", "rhineland",
                            "württemberg", "mecklenburg", "palatin", "hesse", "saxony")):
        return "Germany"
    if "netherlands" in q or "holland" in q:
        return "Netherlands"
    return None


def in_america(p):
    q = (p or "").lower()
    return ("united states" in q or "colonial america" in q
            or "new netherland" in q or "colony" in q)


def year(*vals):
    for v in vals:
        m = re.search(r"\b(1[0-9]{3})\b", v or "")
        if m:
            return int(m.group(1))


def load():
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT generation, birth_place, death_place, birth_date, death_date, "
        "lifespan FROM fs_persons WHERE deleted=0").fetchall()
    db.close()

    stream = collections.defaultdict(collections.Counter)
    for r in rows:
        g = region_of(r["death_place"] or "")
        if g and r["generation"] is not None:
            stream[r["generation"]][g] += 1

    # A death in America before Jamestown is a place-name standardiser artefact.
    imm = [r for r in rows
           if nation_of(r["birth_place"]) and in_america(r["death_place"])
           and (year(r["death_date"], "") or 9999) >= 1607
           and (year(r["birth_date"], "") or 9999) >= 1500]

    def born(r):
        return year(r["birth_date"], r["lifespan"]) or 0

    counts = {
        "england": sum(1 for r in imm
                       if nation_of(r["birth_place"]) in ("England", "Wales")
                       and born(r) < 1700),
        "dutch": sum(1 for r in imm if nation_of(r["birth_place"]) == "Netherlands"),
        "german": sum(1 for r in imm if nation_of(r["birth_place"]) == "Germany"),
        "ulster": sum(1 for r in imm
                      if nation_of(r["birth_place"]) in ("Ulster", "Ireland")
                      and born(r) < 1800),
        "late": sum(1 for r in imm if born(r) >= 1800),
    }
    def crossing_of(r):
        o = nation_of(r["birth_place"])
        if not o or not in_america(r["death_place"]):
            return None
        if (year(r["death_date"], "") or 9999) < 1607:
            return None
        b = year(r["birth_date"], r["lifespan"]) or 0
        if b >= 1800:
            return "V · Industrial"
        return {"England": "I · Great Migration", "Wales": "I · Great Migration",
                "Scotland": "I · Great Migration",
                "Netherlands": "II · New Netherland", "Germany": "III · Palatines",
                "Ulster": "IV · Ulster Scots", "Ireland": "IV · Ulster Scots"}.get(o)

    flows = collections.Counter()
    for r in imm:
        o = nation_of(r["birth_place"])
        label = next((name for name, _, keys in ORIGINS if o in keys), None)
        if not label:
            continue
        place = r["death_place"] or ""
        land = next((name for name, keys in LANDINGS
                     if any(k in place for k in keys)), "Elsewhere")
        flows[(label, land)] += 1
    # ── ancestral lines, tagged by crossing ────────────────────────────────
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    gen = {r["pid"]: r["generation"] for r in db.execute(
        "SELECT pid, generation FROM fs_persons WHERE deleted=0")}
    imm_tag = {}
    for r in db.execute("SELECT pid, birth_place, death_place, birth_date, death_date, "
                        "lifespan FROM fs_persons WHERE deleted=0"):
        c = crossing_of(r)
        if c:
            imm_tag[r["pid"]] = c
    couples = {r["couple_id"]: (r["parent1_pid"], r["parent2_pid"])
               for r in db.execute("SELECT couple_id, parent1_pid, parent2_pid FROM fs_couples")}
    up = collections.defaultdict(list)
    for e in db.execute("SELECT child_couple_id, parent_couple_id FROM fs_edges"):
        up[e["child_couple_id"]].append(e["parent_couple_id"])
    db.close()

    order, seen = [ROOT_COUPLE], {ROOT_COUPLE}
    i = 0
    while i < len(order):
        c = order[i]; i += 1
        for p in up.get(c, []):
            if p not in seen:
                seen.add(p); order.append(p)
    tags = collections.defaultdict(set)
    for c in order:
        for pid in couples.get(c, ()):
            if pid in imm_tag:
                tags[c].add(imm_tag[pid])
    for c in order:                      # child -> parent, so ancestors inherit
        for p in up.get(c, []):
            tags[p] |= tags[c]

    lines = collections.defaultdict(collections.Counter)
    placed = set()
    for c in order:
        for pid in couples.get(c, ()):
            if not pid or pid in placed:
                continue
            placed.add(pid)
            g = gen.get(pid)
            if g is None or g > 14:
                continue
            t = tags[c]
            lines[g]["several" if len(t) > 1 else (next(iter(t)) if t else "American")] += 1

    return stream, counts, len(imm), flows, lines


def smooth(points):
    """A path through points with horizontal-tangent cubic segments."""
    d = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        cx = (x0 + x1) / 2
        d.append(f"C {cx:.1f} {y0:.1f} {cx:.1f} {y1:.1f} {x1:.1f} {y1:.1f}")
    return " ".join(d)


def streamgraph(stream):
    """Composition by generation. Height is constant and each generation is
    normalised to its own total — absolute widths made the later generations
    (n=28, n=12, n=3) invisible, which is where the whole westward story is.
    Cohort size is carried by the printed n above each column instead."""
    gens = [g for g in sorted(stream, reverse=True) if 2 <= g <= 14
            and sum(stream[g].values()) >= 3]
    W, H, PAD_L, PAD_R, PAD_T, PAD_B = 1000, 314, 40, 40, 46, 34
    inner_h = H - PAD_T - PAD_B
    xs = [PAD_L + (W - PAD_L - PAD_R) * i / (len(gens) - 1) for i in range(len(gens))]

    lower = [PAD_T + inner_h] * len(gens)
    parts = []
    for name, colour, _ in REGIONS:
        upper = []
        for i, g in enumerate(gens):
            tot = sum(stream[g].values())
            share = stream[g][name] / tot if tot else 0
            upper.append(lower[i] - share * inner_h)
        fwd = smooth(list(zip(xs, upper)))
        back = smooth(list(zip(reversed(xs), reversed(lower)))).replace("M", "L", 1)
        parts.append(f'<path d="{fwd} {back} Z" fill="{colour}"/>')
        lower = upper[:]

    labels = "".join(
        f'<text x="{x:.1f}" y="{H - PAD_B + 15}" text-anchor="middle" '
        f'class="ax">{g}</text>' for x, g in zip(xs, gens))
    ticks = "".join(
        f'<text x="{x:.1f}" y="{PAD_T - 8}" text-anchor="middle" class="ax-n">'
        f'{sum(stream[g].values())}</text>' for x, g in zip(xs, gens))

    # war markers, placed on the boundary before the generation that fought
    MARKS = [(7, "the Revolution"), (4, "the Civil War")]
    rule = ""
    for g, label in MARKS:
        if g not in gens:
            continue
        i = gens.index(g)
        bx = (xs[i] + xs[i - 1]) / 2
        rule += (f'<line x1="{bx:.1f}" y1="{PAD_T}" x2="{bx:.1f}" y2="{H - PAD_B}" '
                 f'stroke="var(--color-bg)" stroke-width="2"/>'
                 f'<line x1="{bx:.1f}" y1="{PAD_T}" x2="{bx:.1f}" y2="{H - PAD_B}" '
                 f'stroke="var(--color-accent)" stroke-width="1" stroke-dasharray="3 3"/>'
                 f'<text x="{bx:.1f}" y="14" text-anchor="middle" '
                 f'class="ax-mark">{label}</text>'
                 f'<line x1="{bx:.1f}" y1="19" x2="{bx:.1f}" y2="{PAD_T - 16}" '
                 f'stroke="var(--color-accent)" stroke-width="1"/>')

    legend = " ".join(
        f'<span><i style="background:{c}"></i>{n}</span>' for n, c, _ in REGIONS)

    return f"""  <figure class="chart-fig">
    <div class="drift-legend">{legend}</div>
    <svg viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="none"
         aria-label="Composition of each generation by the region of the country its members died in, from the fourteenth generation back to the second. New England fills almost the whole band in the deep generations, collapses between the eighth and the seventh, and is replaced first by the Mid-Atlantic, then the Midwest, then the West.">
      {''.join(parts)}
      {rule}
      {ticks}
      {labels}
      <text x="{PAD_L}" y="{H - 4}" class="ax-t">deepest generation</text>
      <text x="{W - PAD_R}" y="{H - 4}" text-anchor="end" class="ax-t">most recent</text>
    </svg>
    <figcaption>Where each generation died, as a share of that generation. The figure
    above each column is how many ancestors it rests on — 497 at the eighth generation,
    three at the second — so the right-hand end is thinner evidence, not a thinner family.
    Read left to right: New England fills the band for six generations, then goes in a
    single step. The two dashed rules are the wars: generation 7 fought the Revolution,
    generation 4 was of age for the Civil War.</figcaption>
  </figure>"""


def bars(stream):
    """The same data as the streamgraph, generation by generation, with exact
    percentages and the n each rests on. The stream shows the shape; this shows
    the numbers, and neither substitutes for the other."""
    gens = [g for g in sorted(stream, reverse=True) if 2 <= g <= 14
            and sum(stream[g].values()) >= 3]
    legend = " ".join(
        f'<span><i style="background:{c}"></i>{n}</span>' for n, c, _ in REGIONS)
    rows = []
    for g in gens:
        tot = sum(stream[g].values())
        mark = {7: "the Revolution", 4: "the Civil War"}.get(g)
        if mark:
            rows.append('    <div class="drift-break"><span></span>'
                        f'<span><em>{mark}</em></span><span></span></div>')
        segs = "".join(
            f'<span style="width:{100 * stream[g][n] / tot:.1f}%;background:{c}"></span>'
            for n, c, _ in REGIONS if stream[g][n])
        rows.append(
            f'    <div class="drift-row"><span class="drift-gen">{g}</span>'
            f'<span class="drift-track">{segs}</span>'
            f'<span class="drift-n">{tot}</span></div>')
    return ('  <div class="drift">\n'
            f'    <div class="drift-legend">{legend}</div>\n'
            + "\n".join(rows) + "\n  </div>")


ORIGINS = [
    ("England", "var(--color-neutral-800)", ("England",)),
    ("Netherlands", "var(--color-accent-300)", ("Netherlands",)),
    ("Germany", "var(--color-accent-600)", ("Germany",)),
    ("Ulster", "var(--color-accent-500)", ("Ulster",)),
    ("Ireland", "var(--color-neutral-500)", ("Ireland",)),
    ("Scotland, Wales &amp; others", "var(--color-neutral-400)",
     ("Scotland", "Wales", "France", "Switzerland", "Bohemia", "Scandinavia")),
]

LANDINGS = [
    ("Massachusetts Bay", ("Massachusetts Bay", "Suffolk, Massachusetts",
                           "Essex, Massachusetts", "Middlesex, Massachusetts",
                           "Norfolk, Massachusetts", "Massachusetts")),
    ("Plymouth Colony", ("Plymouth Colony", "Plymouth, Plymouth", "Barnstable",
                         "Bristol, Plymouth")),
    ("Connecticut", ("Connecticut",)),
    ("New York &amp; New Netherland", ("New York", "New Netherland")),
    ("Pennsylvania", ("Pennsylvania",)),
    ("Rhode Island", ("Rhode Island",)),
    ("Elsewhere", ()),
]


def sankey(flows):
    """Origin against landing place, everyone included.

    An earlier version dropped England for legibility, which was wrong twice
    over: it hid the biggest fact on the chart, and any reader's first question
    is where England went. Instead the canvas is tall enough that England's
    86% can be a slab and the six minority origins still get separated nodes
    and readable labels. Gaps are fixed in pixels rather than proportional, so
    a three-person origin is still a labelled node."""
    W = 1000
    TOP, BOT, NODE_W, GAP = 42, 34, 12, 30
    LX, RX = 176, W - 216
    total = sum(flows.values())

    src_tot = {o: sum(n for (a, _), n in flows.items() if a == o) for o, _, _ in ORIGINS}
    dst_tot = {d: sum(n for (_, b), n in flows.items() if b == d) for d, _ in LANDINGS}
    src = [o for o in ORIGINS if src_tot[o[0]]]
    dst = [d for d in LANDINGS if dst_tot[d[0]]]

    # A fixed flow height, with generous fixed gaps. Scaling the canvas until the
    # smallest node was tall enough produced a 3,000px figure; separation between
    # labels comes from the gap, not from the node height.
    usable = 760.0
    H = int(usable + TOP + BOT + GAP * (max(len(src), len(dst)) - 1))

    def stack(items, totals):
        y, out = TOP, {}
        for it in items:
            k = it[0]
            h = usable * totals[k] / total
            out[k] = [y, h, y]
            y += h + GAP
        return out

    L, R = stack(src, src_tot), stack(dst, dst_tot)

    ribbons = []
    for name, colour, _ in ORIGINS:
        for dname, _ in LANDINGS:
            n = flows.get((name, dname), 0)
            if not n:
                continue
            h = usable * n / total
            y0, y1 = L[name][2], R[dname][2]
            L[name][2] += h
            R[dname][2] += h
            cx = (LX + NODE_W + RX) / 2
            ribbons.append(
                f'<path d="M {LX + NODE_W} {y0:.1f} '
                f'C {cx} {y0:.1f} {cx} {y1:.1f} {RX} {y1:.1f} '
                f'L {RX} {y1 + h:.1f} '
                f'C {cx} {y1 + h:.1f} {cx} {y0 + h:.1f} {LX + NODE_W} {y0 + h:.1f} Z" '
                f'fill="{colour}" opacity="0.44"/>')

    nodes = []
    for name, colour, _ in src:
        y, h, _ = L[name]
        ty = y + h / 2
        nodes.append(
            f'<rect x="{LX}" y="{y:.1f}" width="{NODE_W}" height="{max(h, 2):.1f}" fill="{colour}"/>'
            f'<text x="{LX - 12}" y="{ty:.1f}" text-anchor="end" class="sk-lab">{name}</text>'
            f'<text x="{LX - 12}" y="{ty + 14:.1f}" text-anchor="end" class="sk-n">'
            f'{src_tot[name]} · {100 * src_tot[name] / total:.0f}%</text>')
    for name, _ in dst:
        y, h, _ = R[name]
        ty = y + h / 2
        nodes.append(
            f'<rect x="{RX}" y="{y:.1f}" width="{NODE_W}" height="{max(h, 2):.1f}" '
            f'fill="var(--color-neutral-700)"/>'
            f'<text x="{RX + NODE_W + 12}" y="{ty:.1f}" class="sk-lab">{name}</text>'
            f'<text x="{RX + NODE_W + 12}" y="{ty + 14:.1f}" class="sk-n">{dst_tot[name]}</text>')

    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="Flow diagram of all {total} immigrant ancestors from country of birth on the left to the colony they died in on the right. England is 86 per cent of the total and flows overwhelmingly into Massachusetts Bay and Plymouth. Below it the minority origins run almost straight across without crossing: the Dutch to New York, the Germans to New York and Pennsylvania, the Ulster Scots and Irish to Pennsylvania.">
      <text x="{LX + NODE_W}" y="20" text-anchor="end" class="ax-t">born</text>
      <text x="{RX}" y="20" class="ax-t">died</text>
      {''.join(ribbons)}
      {''.join(nodes)}
    </svg>
    <figcaption>All {total} ancestors who crossed an ocean, from the country they were born
    in to the colony they died in. Two things at once. <b>England is 86% of everything</b>
    — that slab at the top is the Great Migration, and it pours almost entirely into
    Massachusetts Bay and Plymouth. And beneath it the ribbons barely cross: the Dutch to
    New York, the Germans to New York and Pennsylvania, the Ulster Scots and Irish to
    Pennsylvania. Five migrations that shared a continent and did not mix.<br><br>
    The one ribbon that does cross is the interesting one — the Netherlands reaching over
    to Plymouth is the <a href="#mayflower">Leiden congregation</a>, English Separatists
    whose children were born in Holland during the exile and who are Dutch only by
    birthplace.</figcaption>
  </figure>"""


LINE_BANDS = [
    ("American", "var(--color-neutral-800)"),
    ("several", "var(--color-neutral-600)"),
    ("V · Industrial", "var(--color-accent-200)"),
    ("IV · Ulster Scots", "var(--color-accent-500)"),
    ("III · Palatines", "var(--color-accent-600)"),
    ("II · New Netherland", "var(--color-accent-300)"),
    ("I · Great Migration", "var(--color-neutral-400)"),
]


def alluvial(lines):
    """Ancestral lines converging. Reading right, each generation halves as
    marriages merge two lines into one, and the coloured bands -- lines that
    still sit at or above an immigrant, so still belong to one crossing --
    dissolve into a single American stream."""
    gens = [g for g in sorted(lines, reverse=True) if 0 <= g <= 14]
    W, H = 1000, 380
    PAD_L, PAD_R, PAD_T, PAD_B = 44, 44, 44, 40
    inner = H - PAD_T - PAD_B
    peak = max(sum(lines[g].values()) for g in gens)
    xs = [PAD_L + (W - PAD_L - PAD_R) * i / (len(gens) - 1) for i in range(len(gens))]

    # Normalised. Absolute widths made the funnel the whole figure and squeezed
    # the merge -- which is the thing being shown -- into a thread at the right.
    # The line counts printed along the top carry the funnel instead.
    totals = [sum(lines[g].values()) for g in gens]
    lower = [PAD_T + inner] * len(gens)
    parts = []
    for name, colour in LINE_BANDS:
        upper = []
        for i, g in enumerate(gens):
            tot = sum(lines[g].values())
            h = inner * lines[g].get(name, 0) / totals[i]
            upper.append(lower[i] - h)
        fwd = smooth(list(zip(xs, upper)))
        back = smooth(list(zip(reversed(xs), reversed(lower)))).replace("M", "L", 1)
        parts.append(f'<path d="{fwd} {back} Z" fill="{colour}" opacity="0.92"/>')
        lower = upper[:]

    counts = "".join(
        f'<text x="{x:.1f}" y="{PAD_T - 10}" text-anchor="middle" class="ax-n">'
        f'{sum(lines[g].values())}</text>' for x, g in zip(xs, gens))
    axis = "".join(
        f'<text x="{x:.1f}" y="{H - PAD_B + 16}" text-anchor="middle" class="ax">{g}</text>'
        for x, g in zip(xs, gens))
    legend = " ".join(
        f'<span><i style="background:{c}"></i>{n}</span>'
        for n, c in reversed(LINE_BANDS))
    return f"""  <figure class="chart-fig">
    <div class="drift-legend">{legend}</div>
    <svg viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="none"
         aria-label="Alluvial diagram of ancestral lines converging. At the fourteenth generation there are 898 separate lines, most of them still belonging to a single crossing. Moving forward in time each generation roughly halves as marriages merge lines, the coloured crossing bands dissolve into one American stream, and by the third generation a single line remains.">
      {''.join(parts)}
      {counts}
      {axis}
      <text x="{PAD_L}" y="{H - 6}" class="ax-t">{max(totals)} separate lines</text>
      <text x="{W - PAD_R}" y="{H - 6}" text-anchor="end" class="ax-t">one person</text>
    </svg>
    <figcaption>Every ancestral line the record can reach, as a share of that generation.
    The figures along the top are how many separate lines there are —
    <b>{max(totals)} at the fourteenth generation, one at the end</b>, because every
    marriage turns two lines into one. The colours are lines that still belong to a single
    crossing, meaning people at or above an immigrant. Watch them give way to a single
    <em>American</em> stream, which takes half the tree by about the tenth generation and
    all of it by the third. <b>Crossing V arrives too late to be anything else</b> — it
    enters at the fourth generation and is absorbed within two.<br><br>
    <em>Several</em> means a line that feeds more than one crossing — the same deep
    ancestor reached down two different immigrant descents. At the fourteenth generation
    that is already 134 people, which is what a hundred people at Plymouth marrying each
    other looks like nine generations later.</figcaption>
  </figure>"""


def crossings_chart(counts):
    """Two encodings, kept apart: when each crossing happened, and how big it
    was. The year range lives in the title line so nothing collides with the
    axis, and the share bar sits below the axis with its own clearance."""
    W, PAD_L, PAD_R, ROW = 1000, 26, 26, 50
    lo, hi = 1600, 1900
    span = W - PAD_L - PAD_R
    total = sum(counts[k] for _, _, _, _, k in CROSSINGS)
    rows, y = [], 18
    for num, name, a, b, key in CROSSINGS:
        n = counts[key]
        x1 = PAD_L + span * (a - lo) / (hi - lo)
        x2 = PAD_L + span * (b - lo) / (hi - lo)
        # rows near the right edge get their label and count mirrored inward,
        # or the year range runs off the viewBox
        near_right = x1 > PAD_L + span * 0.62
        if near_right:
            label = (f'<text x="{x2:.1f}" y="0" text-anchor="end" class="cx-lab">'
                     f'{num} · {name}<tspan class="cx-yr" dx="10">{a}–{b}</tspan></text>')
            count = f'<text x="{x1 - 9:.1f}" y="19" text-anchor="end" class="cx-num">{n}</text>'
        else:
            label = (f'<text x="{x1:.1f}" y="0" class="cx-lab">{num} · {name}'
                     f'<tspan class="cx-yr" dx="10">{a}–{b}</tspan></text>')
            count = f'<text x="{x2 + 9:.1f}" y="19" class="cx-num">{n}</text>'
        rows.append(
            f'<g transform="translate(0,{y})">{label}'
            f'<rect x="{x1:.1f}" y="8" width="{max(x2 - x1, 3):.1f}" height="14" rx="1" '
            f'fill="var(--color-accent-600)"/>{count}</g>')
        y += ROW

    axis_y = y + 2
    axis = "".join(
        f'<text x="{PAD_L + span * (t - lo) / (hi - lo):.1f}" y="{axis_y + 14}" '
        f'text-anchor="middle" class="ax">{t}</text>'
        for t in range(1600, 1901, 50))

    bar_y = axis_y + 44
    sx, seg = PAD_L, []
    for num, name, _, _, key in CROSSINGS:
        w = span * counts[key] / total
        shade = "var(--color-neutral-800)" if num == "I" else "var(--color-accent-600)"
        seg.append(f'<rect x="{sx:.2f}" y="{bar_y}" width="{max(w, 1.0):.2f}" '
                   f'height="17" fill="{shade}"/>')
        if w > 90:
            seg.append(f'<text x="{sx + 10:.1f}" y="{bar_y + 12}" class="cx-in">'
                       f'{num} — {100 * counts[key] / total:.0f}%</text>')
        sx += w
    caption = (f'<text x="{PAD_L}" y="{bar_y - 9}" class="ax-t">'
               f'share of all {total} crossings</text>'
               f'<text x="{W - PAD_R}" y="{bar_y - 9}" text-anchor="end" class="ax-t">'
               f'II–V together: {100 * (total - counts["england"]) / total:.0f}%</text>')
    H = bar_y + 26
    return f"""  <figure class="chart-fig">
    <svg viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="xMidYMid meet"
         aria-label="The five crossings on a year axis from 1600 to 1900, with a stacked bar beneath showing that the Great Migration accounts for about seven-eighths of all immigrant ancestors.">
      {''.join(rows)}
      <line x1="{PAD_L}" y1="{axis_y}" x2="{W - PAD_R}" y2="{axis_y}"
            stroke="var(--color-divider)" stroke-width="1"/>
      {axis}
      {caption}
      {''.join(seg)}
    </svg>
    <figcaption>Above, when each crossing happened. Below, the same five as a share of all
    {total} people who made one. The two long silences — 1664 to 1709, and 1775 to 1840 —
    are as much the story as the arrivals.</figcaption>
  </figure>"""


def main():
    stream, counts, total, flows, lines = load()
    page = open(PAGE, encoding="utf-8").read()
    for marker, svg in (("stream", streamgraph(stream)),
                        ("bars", bars(stream)),
                        ("sankey", sankey(flows)),
                        ("alluvial", alluvial(lines)),
                        ("crossings", crossings_chart(counts))):
        pat = re.compile(f"(<!-- CHART:{marker} -->).*?(<!-- /CHART:{marker} -->)", re.S)
        if not pat.search(page):
            print(f"  ! no marker for {marker} in index.html", file=sys.stderr)
            continue
        page = pat.sub(lambda m: f"{m.group(1)}\n{svg}\n  {m.group(2)}", page)
    open(PAGE, "w", encoding="utf-8").write(page)
    print(f"  charts written · {total} immigrants · "
          + ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
