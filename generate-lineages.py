#!/usr/bin/env python3
"""Build the lineage appendix, and link every named person on the record to it.

Every person the record names gets one entry showing how the line actually runs
from them to the present. The entry is real HTML in an appendix at the foot of
the page, so it works with JavaScript switched off and is reachable by anchor;
site.js then reads that same markup into a dialog when a name is clicked. One
copy of the truth, two ways to read it.

Two rules the generator enforces, because both are easy to get wrong by hand:

  * No living person is named. Chains stop at the last person with a death date
    and record only how many generations follow.
  * Collateral relatives do not get a fake descent. Somebody who married in, or
    who is a sibling of an ancestor, is labelled as such and pointed at the
    person who actually carries the line.

    python3 generate-lineages.py [--check]
"""
import collections
import html
import os
import re
import sqlite3
import sys

DB = os.path.expanduser("~/.local/share/familysearch-pp-cli/data.db")
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "index.html")
ROOT_COUPLE = "PXFK-VML_"

BEGIN = "<!-- LINEAGES:begin -->"
END = "<!-- LINEAGES:end -->"

# Records whose "name" is a place, a title fragment, or otherwise not a person.
# They match page text by accident and must never be linked.
JUNK = re.compile(r"^(Mr|Mrs|Miss|Lady|Sir)\.?\s*(Essex|Yorkshire|Thomas|Russell|Esse)\b"
                  r"|^(Scotland|Yorkshire|Galloway|Angus|Atholl|Buchan|Mar|Moray)$")

TITLES = (r"Capt\.?|Captain Lieutenant|Captain|Rev\.?|Dr\.?|Lt\.?|Lieut\.?|Deacon|Hon\.?|"
          r"Sgt\.?|Col\.?|Sir|Elder|Ensign|Governor|Gov\.?|King|Brig\.?|General")

# The tree stores maiden names; the record calls some women by the married name
# they are known to history under. Without these the page's own phrasing --
# "Rebecca Nurse", "Mary Esty" -- matches no record and gets no entry at all.
ALIASES = {
    "Rebecca Nurse": "9421-W84",     # b. Rebecca Towne, hanged 19 July 1692
    "Mary Esty": "LZLN-LNC",         # b. Mary Towne, her sister, hanged 22 September
    "Mary Elizabeth Gilmore Gore": "KZL1-9LT",
}


def connect(db_path):
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        con.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        return con
    except sqlite3.OperationalError:
        return sqlite3.connect(db_path)


def living(person):
    return "Living" in (person.get("lifespan") or "")


def load():
    db = connect(DB)
    db.row_factory = sqlite3.Row
    people = {r["pid"]: dict(r) for r in db.execute(
        "SELECT pid, name, lifespan, birth_place, death_place, generation, source_count "
        "FROM fs_persons WHERE deleted=0")}
    couples = {r["couple_id"]: dict(r) for r in db.execute("SELECT * FROM fs_couples")}
    up = collections.defaultdict(list)
    for r in db.execute("SELECT * FROM fs_edges"):
        up[r["child_couple_id"]].append((r["parent_couple_id"], r["via"]))
    db.close()

    # Walk down from the root couple, remembering how each couple was reached.
    prev = {ROOT_COUPLE: None}
    queue = collections.deque([ROOT_COUPLE])
    while queue:
        child = queue.popleft()
        for parent, via in up.get(child, []):
            if parent not in prev:
                prev[parent] = (child, via)
                queue.append(parent)

    member_of = collections.defaultdict(list)
    for cid, c in couples.items():
        for key in ("parent1_pid", "parent2_pid"):
            if c.get(key):
                member_of[c[key]].append(cid)
    return people, couples, prev, member_of


def descent(pid, people, couples, prev, member_of):
    """The line from pid to the present, as a list of person dicts."""
    reachable = [c for c in member_of.get(pid, []) if c in prev]
    if not reachable:
        return None
    cur = reachable[0]
    chain = []
    while prev[cur] is not None:
        child_couple, via = prev[cur]
        heir = couples[child_couple]["parent1_pid" if via == "parent1" else "parent2_pid"]
        if heir:
            chain.append(people[heir])
        cur = child_couple
    return chain


def collateral_note(pid, people, couples, prev, member_of):
    """For someone off the direct line, name the person who carries it."""
    for cid in member_of.get(pid, []):
        c = couples[cid]
        spouse = c["parent2_pid"] if c["parent1_pid"] == pid else c["parent1_pid"]
        if spouse and descent(spouse, people, couples, prev, member_of):
            return f"married into the line, through {people[spouse]['name']}"
    return None


def rel_label(steps):
    """steps = how many generations from this person down to the record's subject."""
    if steps <= 0:
        return ""
    if steps == 1:
        return "parent"
    if steps == 2:
        return "grandparent"
    if steps == 3:
        return "great-grandparent"
    n = steps - 2
    suf = {1: "st", 2: "nd", 3: "rd"}.get(n if n % 100 not in (11, 12, 13) else 0, "th")
    return f"{n}{suf} great-grandparent"


def e(s):
    return html.escape(s or "", quote=False)


FS_PERSON = "https://www.familysearch.org/tree/person/details/"


def person_line(p, link_id=True):
    """Name, dates, and the FamilySearch identifier the record was read from.

    The identifier is the only thing here that lets a reader check the claim
    themselves, so it is on every line rather than only on the subject.
    """
    span = p.get("lifespan") or ""
    out = e(p["name"])
    if span:
        out += f' <span class="ln-yr">{e(span)}</span>'
    pid = p.get("pid") or ""
    if pid:
        if link_id:
            out += (f' <a class="ln-pid" href="{FS_PERSON}{e(pid)}" '
                    f'rel="noopener" target="_blank">{e(pid)}</a>')
        else:
            out += f' <span class="ln-pid">{e(pid)}</span>'
    return out


def build_entries(people, couples, prev, member_of, page_text):
    """Resolve the names the page actually uses, and describe each one's line."""
    by_name = collections.defaultdict(list)
    for pid, p in people.items():
        by_name[p["name"]].append(pid)

    entries = {}
    for name, pids in by_name.items():
        if len(name) < 8 or name.startswith("*") or JUNK.search(name):
            continue
        core = re.sub(rf"^({TITLES})\s+", "", name).strip()
        if len(core) < 8 or core not in page_text:
            continue
        if core[0].islower() or len(core.split()) < 2:
            continue          # "of Whalley", bare given names
        pid = max(pids, key=lambda x: (people[x]["source_count"] or 0))
        if living(people[pid]):
            continue
        chain = descent(pid, people, couples, prev, member_of)
        entries[core] = {"pid": pid, "person": people[pid], "chain": chain,
                         "note": None if chain else
                         collateral_note(pid, people, couples, prev, member_of)}

    for alias, pid in ALIASES.items():
        if alias in page_text and pid in people and alias not in entries:
            entries[alias] = {"pid": pid, "person": people[pid],
                              "chain": descent(pid, people, couples, prev, member_of),
                              "note": None}

    # A truncated record ("Anna Barbara") matches inside a fuller one
    # ("Anna Barbara Riemensnyder") and would steal its link. Drop the prefixes.
    for core in list(entries):
        if any(other != core and other.startswith(core + " ") for other in entries):
            del entries[core]

    # One article per person. An alias and a maiden name can resolve to the same
    # record ("Mary Esty" and "Mary Towne"), and two articles would then carry
    # the same id, which is invalid and breaks the dialog lookup. Keep whichever
    # spelling the page uses first, so the link lands where the reader is.
    seen = {}
    for core in sorted(entries, key=lambda k: page_text.find(k)):
        pid = entries[core]["pid"]
        if pid in seen:
            del entries[core]
        else:
            seen[pid] = core
    return entries


def render_entry(core, ent):
    p, chain = ent["person"], ent["chain"]
    out = [f'  <article class="lineage" id="lin-{e(ent["pid"])}">',
           f'    <h3>{person_line(p)}</h3>']
    born = p.get("birth_place") or ""
    died = p.get("death_place") or ""
    if born or died:
        bits = []
        if born:
            bits.append(f"b. {e(born)}")
        if died:
            bits.append(f"d. {e(died)}")
        out.append(f'    <p class="ln-place">{" · ".join(bits)}</p>')

    if not chain:
        why = ent["note"] or ("not on a traced descent line in this record — "
                              "a relative rather than an ancestor")
        out.append(f'    <p class="ln-rel ln-collateral">Not a direct ancestor: {e(why)}.</p>')
        out.append("  </article>")
        return "\n".join(out)

    named = [q for q in chain if not living(q)]
    hidden = len(chain) - len(named)
    out.append(f'    <p class="ln-rel">{rel_label(len(chain))} '
               f'<span class="ln-steps">· {len(chain)} generations</span></p>')
    out.append('    <ol class="ln-chain">')
    out.append(f'      <li class="ln-head">{person_line(p)}</li>')
    for q in named:
        out.append(f"      <li>{person_line(q)}</li>")
    if hidden:
        word = "generation" if hidden == 1 else "generations"
        out.append(f'      <li class="ln-living">then {hidden} living {word}, '
                   f"not named here</li>")
    out.append("    </ol>")
    out.append("  </article>")
    return "\n".join(out)


def render_appendix(entries):
    lin = sum(1 for v in entries.values() if v["chain"])
    col = len(entries) - lin
    body = [BEGIN,
            '<section data-anchor id="lineages">',
            '  <p class="kicker">Appendix · every name on this page</p>',
            "  <h2>How each person connects</h2>",
            f'  <p class="lead">Every person the record names, and the line that runs from '
            f'them to the present. {lin} carry the descent; {col} are relatives who do not, '
            f'and say so. Click any name in the text above to open its line, or read them '
            f'here.</p>',
            '  <p class="note">Chains stop at the last person with a death date. No living '
            "individual is named, dated or placed anywhere on this page.</p>",
            '  <div class="ln-grid">']
    for core in sorted(entries, key=lambda k: (entries[k]["chain"] is None, k.split()[-1])):
        body.append(render_entry(core, entries[core]))
    body.append("  </div>")
    body.append("</section>")
    body.append(END)
    return "\n".join(body)


HEADINGS = ("h1", "h2", "h3", "h4", "title")


def _linkable(page, start):
    """True if this offset is body text we may wrap in an anchor."""
    before = page[:start]
    if before.rfind("<") > before.rfind(">"):
        return False                                    # inside a tag or attribute
    if before.rfind("<a ") > before.rfind("</a>"):
        return False                                    # already inside a link
    for tag in HEADINGS:
        if before.rfind(f"<{tag}") > before.rfind(f"</{tag}>"):
            return False                                # inside a heading
    return True


def link_names(page, entries):
    """Wrap the first mention of each person in a link to their entry.

    Longest names first, so "Anna Barbara Riemensnyder" claims its text before a
    shorter name can match part of it.

    The word boundaries deliberately allow a tag on either side: names are
    routinely wrapped or followed by markup, as in `James Chilton<span
    class="yr">`, and excluding `<` here silently made every such name
    unlinkable. Whether an offset is really body text is _linkable's job.

    A short name is only blocked from matching when the words that follow would
    extend it into some *other* entry's name. Checking against the entry list
    rather than "is the next word capitalised" keeps married surnames, as in
    "Mary Elizabeth Gilmore Gore", linked to the right person.
    """
    names = sorted(entries, key=len, reverse=True)
    done = set()
    for core in names:
        pid = entries[core]["pid"]
        if pid in done:
            continue
        longer = [n for n in names if n != core and n.startswith(core + " ")]
        pattern = re.compile(r"(?<![\w-])" + re.escape(core) + r"(?![\w-])")
        for m in pattern.finditer(page):
            if BEGIN in page[:m.start()] or not _linkable(page, m.start()):
                continue
            if any(page.startswith(n, m.start()) for n in longer):
                continue
            page = (page[:m.start()]
                    + f'<a class="lin" href="#lin-{pid}" data-lin="{pid}">{core}</a>'
                    + page[m.end():])
            done.add(pid)
            break
    return page, len(done)


def main():
    people, couples, prev, member_of = load()
    page = open(PAGE, encoding="utf-8").read()

    stripped = re.sub(r"<svg.*?</svg>", "", page, flags=re.S)
    if BEGIN in stripped:
        stripped = stripped[:stripped.index(BEGIN)]
    page_text = re.sub(r"<[^>]+>", " ", stripped)

    entries = build_entries(people, couples, prev, member_of, page_text)

    # Remove any previous appendix and previous links, then rebuild both.
    # Consume the trailing blank lines too, or each run adds two more.
    page = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n*", "", page, flags=re.S)
    page = re.sub(r'<a class="lin" href="#lin-[^"]+" data-lin="[^"]+">(.*?)</a>',
                  r"\1", page, flags=re.S)

    page, linked = link_names(page, entries)
    appendix = render_appendix(entries)

    anchor = '<section data-anchor id="contribute">'
    if anchor not in page:
        raise SystemExit("could not find the contribute section to insert before")
    page = page.replace(anchor, appendix + "\n\n" + anchor, 1)

    if "--check" in sys.argv:
        cur = open(PAGE, encoding="utf-8").read()
        if cur != page:
            print("lineage appendix is stale — run generate-lineages.py")
            sys.exit(1)
        print("lineage appendix is current")
        return

    open(PAGE, "w", encoding="utf-8").write(page)
    lin = sum(1 for v in entries.values() if v["chain"])
    print(f"lineages written · {len(entries)} people "
          f"({lin} with a descent, {len(entries) - lin} collateral) · {linked} linked in text")


if __name__ == "__main__":
    main()
