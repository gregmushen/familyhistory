#!/usr/bin/env python3
"""Generate ruled-out.html from the research layer in the FamilySearch mirror.

The page used to be hand-maintained, which meant its entry counts drifted every
time a finding was added. Everything factual now comes from fs_findings and
fs_sources; only the editorial framing below is written here.

    python3 generate-ruled-out.py [--check]

--check exits non-zero if the file on disk differs from what the database would
produce, so it can gate a commit.
"""
import html
import os
import sqlite3
import sys

DB = os.path.expanduser("~/.local/share/familysearch-pp-cli/data.db")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ruled-out.html")
ASSET_V = "v=92"

# Section order, and the editorial lead that introduces each. The entries
# themselves are generated.
SECTIONS = [
    ("people",    "Rejected", "People who are not ancestors",
     "Names that attach themselves to a tree because they are famous, or because "
     "the spelling matched."),
    ("dates",     "Rejected", "Impossible dates",
     "Deaths recorded in colonies that did not exist yet. Excluded from the "
     "westward-drift analysis on the main record."),
    ("faces",     "Doubtful", "Faces that cannot be theirs",
     "Costume dates a picture. Three of these were ruled out on the wig alone, and "
     "one on the shape of a dress."),
    ("legends",   "Doubtful", "Legends", None),
    ("conflicts", "Unsettled", "Records that disagree",
     "Neither source is obviously the weaker. The main record carries both."),
    ("unproven",  "Unsettled", "Claimed, not shown",
     "Longstanding and specific, and still without the document that would settle "
     "them."),
]

# verdict + section -> the chip shown against an entry
CHIP = {
    ("refuted", "people"): ("v-out", "Rejected"),
    ("refuted", "dates"): ("v-out", "Excluded"),
    ("refuted", "faces"): ("v-out", "Not him"),
    ("refuted", "legends"): ("v-legend", "Legend"),
    ("unproven", "people"): ("v-open", "Not published"),
    ("unproven", "unproven"): ("v-open", "Unproven"),
    ("unresolved", "conflicts"): ("v-conflict", "Unresolved"),
    ("supported", "unproven"): ("v-open", "Single source"),
}

FACE_PLATES = [
    ("john-lothrop.jpg", "Commemorative badge showing a clergyman in a powdered wig.",
     "Circulated as John Lothropp, d. 1653."),
    ("thomas-dudley.jpg", "Engraved bust of a man in a full-bottomed periwig.",
     "Circulated as Thomas Dudley, d. 1653."),
    ("howland.jpg", "General Society of Mayflower Descendants emblem.",
     "Attached to five of the nine passengers."),
]

ROLE_WORD = {"supports": "Supported by", "refutes": "Ruled out by",
             "conflicts": "In conflict", "context": "Context"}


def connect(db_path):
    """Read-only if possible, plain read-write if not.

    A WAL database needs a -shm file, and SQLite cannot create one through a
    mode=ro handle. After the hydrator exits cleanly it checkpoints and removes
    -shm, so mode=ro then fails with "unable to open database file" even though
    the file is perfectly readable. Fall back rather than die; nothing here
    writes.
    """
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        return con
    except sqlite3.OperationalError:
        return sqlite3.connect(db_path)


def e(s):
    return html.escape(s, quote=False) if s else ""


def load():
    db = connect(DB)
    db.row_factory = sqlite3.Row
    findings = {}
    for r in db.execute(
        "SELECT finding_id, section, subject_kind, pid, subject_label, claim, "
        "verdict, reasoning, provenance, title, note_label, note FROM fs_findings "
        "WHERE section IS NOT NULL AND superseded_by IS NULL "
        "ORDER BY section, finding_id"
    ):
        findings.setdefault(r["section"], []).append(dict(r))
    # The render loop walks SECTIONS, so a finding filed under any other section
    # is loaded here and then quietly never drawn. That is exactly how eleven
    # findings went missing once: `section` is a ruled-out bucket, and they had
    # been filed with index.html anchor names instead. Fail loudly.
    unknown = set(findings) - {s[0] for s in SECTIONS}
    if unknown:
        raise SystemExit(
            "unknown section(s) in fs_findings: " + ", ".join(sorted(unknown))
            + "\nsection must be one of: " + ", ".join(s[0] for s in SECTIONS)
            + " (or NULL for a finding that does not belong on ruled-out)")
    names = {r["pid"]: r["name"] for r in db.execute(
        "SELECT pid, name FROM fs_persons WHERE deleted=0")}
    srcs = {}
    for r in db.execute(
        "SELECT fs.finding_id, s.title, s.creator, s.year, s.url, fs.role, fs.locator "
        "FROM fs_finding_sources fs JOIN fs_sources s USING (source_id) "
        "ORDER BY CASE fs.role WHEN 'refutes' THEN 0 WHEN 'conflicts' THEN 1 "
        "WHEN 'supports' THEN 2 ELSE 3 END"
    ):
        srcs.setdefault(r["finding_id"], []).append(dict(r))
    db.close()
    return findings, names, srcs


def heading(f, names):
    return f["title"] or f["subject_label"] or names.get(f["pid"], "Unattributed")


def render_sources(rows):
    if not rows:
        return ""
    out = []
    for r in rows:
        cite = f'<a href="{e(r["url"])}" rel="noopener">{e(r["title"])}</a>' if r["url"] \
            else f'<b>{e(r["title"])}</b>'
        bits = [cite]
        if r["creator"]:
            bits.append(e(r["creator"]))
        if r["year"]:
            bits.append(e(r["year"]))
        if r["locator"]:
            bits.append(e(r["locator"]))
        out.append(f'<dd><em>{ROLE_WORD.get(r["role"], r["role"])}:</em> '
                   + " · ".join(bits) + "</dd>")
    return "<dt>Sources</dt>\n      " + "\n      ".join(out)


def render():
    findings, names, srcs = load()
    total = sum(len(v) for v in findings.values())
    counts = {k: len(v) for k, v in findings.items()}
    by_verdict = {}
    for rows in findings.values():
        for f in rows:
            by_verdict[f["verdict"]] = by_verdict.get(f["verdict"], 0) + 1

    nav = []
    for group, sects in [("Rejected", ["people", "dates"]),
                         ("Doubtful", ["faces", "legends"]),
                         ("Unsettled", ["conflicts", "unproven"])]:
        items = []
        for sid, _, title, _ in SECTIONS:
            if sid not in sects or not counts.get(sid):
                continue
            n = counts[sid]
            items.append(
                f'<li><a data-navlink href="#{sid}">{e(title)}'
                f'<span class="sub">{n} {"entry" if n == 1 else "entries"}</span></a></li>')
        if items:
            nav.append(f'    <div class="index-group">\n'
                       f'      <p class="index-label">{group}</p>\n'
                       f'      <ul>\n        ' + "\n        ".join(items) +
                       "\n      </ul>\n    </div>")

    body = []
    for sid, kicker, title, lead in SECTIONS:
        rows = findings.get(sid)
        if not rows:
            continue
        body.append(f'<section data-anchor id="{sid}">')
        body.append(f'  <p class="kicker">{kicker}</p>')
        body.append(f"  <h2>{e(title)}</h2>")
        if lead:
            body.append(f'  <p class="lead">{e(lead)}</p>')
        if sid == "faces":
            body.append('  <div class="trio">')
            for fn, alt, cap in FACE_PLATES:
                body.append(
                    f'    <figure><img class="plate" width="200" height="200" '
                    f'src="assets/img/{fn}" alt="{e(alt)}">'
                    f"<figcaption>{e(cap)}</figcaption></figure>")
            body.append("  </div>")
        for f in rows:
            cls, label = CHIP.get((f["verdict"], sid), ("v-open", f["verdict"].title()))
            body.append('  <article class="claim">')
            body.append(f'    <div class="claim-head"><h3>{e(heading(f, names))}</h3>'
                        f'<span class="verdict {cls}">{label}</span></div>')
            body.append("    <dl>")
            body.append(f"      <dt>The claim</dt>\n      <dd>{e(f['claim'])}</dd>")
            if f["provenance"]:
                body.append(f"      <dt>Where it came from</dt>\n      <dd>{e(f['provenance'])}</dd>")
            verdict_label = {"refuted": "How it was ruled out",
                             "unresolved": "The gap",
                             "unproven": "What is missing",
                             "supported": "What is missing",
                             "tradition": "What is missing",
                             "documented": "The evidence"}.get(f["verdict"], "Assessment")
            body.append(f"      <dt>{verdict_label}</dt>\n      <dd>{e(f['reasoning'])}</dd>")
            if f["note"]:
                body.append(f"      <dt>{e(f['note_label'])}</dt>\n      <dd>{e(f['note'])}</dd>")
            s = render_sources(srcs.get(f["finding_id"], []))
            if s:
                body.append("      " + s)
            body.append("    </dl>")
            body.append("  </article>")
        body.append("</section>\n")

    rejected = by_verdict.get("refuted", 0)
    faces = counts.get("faces", 0)
    still_open = by_verdict.get("unproven", 0) + by_verdict.get("unresolved", 0)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ruled out — Mushen Family History</title>
<meta name="description" content="Everything this family record considered and rejected: false ancestors, impossible dates, portraits that cannot be their subjects, legends, unresolved conflicts, and claims still unproven.">
<meta name="color-scheme" content="light">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="assets/classical.css?{ASSET_V}">
<link rel="stylesheet" href="assets/site.css?{ASSET_V}">
<script>
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches
      && 'IntersectionObserver' in window) {{
    document.documentElement.classList.add('reveal-enabled');
  }}
</script>
</head>
<body>

<!-- Generated by generate-ruled-out.py from fs_findings. Do not edit by hand. -->

<a class="skip-link" href="#top">Skip to the list</a>

<aside data-rail aria-label="Index">
  <div class="rail-head">
    <a class="wordmark" href="/">Mushen</a>
    <p class="rail-sub">Ruled out</p>
  </div>

  <nav data-index aria-label="Sections">
{chr(10).join(nav)}
    <div class="index-group">
      <p class="index-label">Elsewhere</p>
      <ul>
        <li><a data-navlink href="/">← The record itself</a></li>
      </ul>
    </div>
  </nav>
</aside>

<main data-main>

<header id="top">
  <p class="kicker">A companion to the record · compiled 2026</p>
  <h1 class="display">Ruled out.</h1>
  <p class="dek">Family histories publish what survived. This is the other half — every
  claim this record considered and threw out, every portrait that turned out to be
  somebody else, and every question still open. {total} entries, each with where it came
  from and how it fell.</p>
  <p class="hint">Nothing on this page is on the main record</p>
</header>

<section class="stats" aria-label="Summary">
  <div class="stat stat--accent"><b>{total}</b><span>Entries</span></div>
  <div class="stat"><b>{rejected}</b><span>Rejected outright</span></div>
  <div class="stat"><b>{faces}</b><span>Wrong faces</span></div>
  <div class="stat"><b>{still_open}</b><span>Still open</span></div>
</section>

{chr(10).join(body)}
<section>
  <p class="grade" style="max-width:64ch">Anything on this page can move to the main record
  the moment a document turns up. That is the point of writing it down.</p>
  <a class="backlink" href="/">← Back to the record</a>

  <footer class="site-foot">
    Mushen family history · compiled 2026 · deceased ancestors only
  </footer>
</section>

</main>

<script src="assets/site.js?{ASSET_V}"></script>
</body>
</html>
"""


if __name__ == "__main__":
    out = render()
    if "--check" in sys.argv:
        cur = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if cur != out:
            print("ruled-out.html is stale — run generate-ruled-out.py")
            sys.exit(1)
        print("ruled-out.html is current")
    else:
        open(OUT, "w", encoding="utf-8").write(out)
        n = out.count('class="claim"')
        print(f"wrote {OUT}  ({n} entries, {len(out) // 1024} KB)")
