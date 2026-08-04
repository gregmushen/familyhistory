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
    who is a sibling of an ancestor, is labeled as such and pointed at the
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
CBEGIN = "<!-- COLLAPSE:begin -->"
CEND = "<!-- COLLAPSE:end -->"

# The couple at the foot of the tree, whose two halves are the paternal and
# maternal lines. Named by couple id so no living person appears in the source.
LAST_COUPLE = "PXFV-YG6_PXFK-QCT"

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
    # The tree spells him Lothrop and the record spells him Lothropp, which left
    # the single most-featured person on the page -- 90 sources, 275 memories,
    # a section of his own -- with no entry at all.
    "John Lothropp": "LZG6-CH7",
    "Rev. John Lothropp": "LZG6-CH7",
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
    return people, couples, prev, member_of, up


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


def build_entries(people, couples, prev, member_of, page_text, force=()):
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

    # People named only inside a generated block still deserve an entry, and
    # must not be discovered *from* that block: matching generated text would
    # make the generator's output depend on its own previous output.
    for pid in force:
        p = people.get(pid)
        if p and not living(p) and p["name"] not in entries:
            entries[p["name"]] = {
                "pid": pid, "person": p, "note": None,
                "chain": descent(pid, people, couples, prev, member_of)}

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
            # Keep the spelling out of the appendix, but remember it: the
            # discarded variant is often the only one that appears in linkable
            # prose. "Rev. John Lothropp" wins the dedupe because it appears in
            # the nav first, and every one of its occurrences is inside a
            # heading or an existing anchor, so the man with the most sources
            # on the page ended up with no link at all.
            entries[seen[pid]].setdefault("also", []).append(core)
            del entries[core]
        else:
            seen[pid] = core
    return entries


def collapse(people, couples, up):
    """Where the paternal and maternal lines turn out to be the same line.

    Walks up from each half of the last couple separately and intersects the
    two sets of ancestors. Distance is counted in generations up each side, so
    the closest shared couple is the most recent point at which the record's
    two halves were already one family.
    """
    def climb(starts):
        depth = {c: 1 for c in starts}
        queue = collections.deque(starts)
        person, couple = {}, {}
        while queue:
            cur = queue.popleft()
            couple[cur] = depth[cur]
            c = couples.get(cur, {})
            for key in ("parent1_pid", "parent2_pid"):
                pid = c.get(key)
                if pid and depth[cur] < person.get(pid, 10 ** 6):
                    person[pid] = depth[cur]
            for parent, _ in up.get(cur, []):
                if parent not in depth:
                    depth[parent] = depth[cur] + 1
                    queue.append(parent)
        return person, couple

    dad = [p for p, via in up.get(LAST_COUPLE, []) if via == "parent1"]
    mom = [p for p, via in up.get(LAST_COUPLE, []) if via == "parent2"]
    dp, dc = climb(dad)
    mp, mc = climb(mom)
    shared_people = set(dp) & set(mp)
    # Sort on the couple id as well. Without it, couples at equal distance come
    # out in set-iteration order, which Python varies per process, and the table
    # reshuffles between runs.
    shared_couples = sorted(set(dc) & set(mc), key=lambda c: (dc[c] + mc[c], dc[c], c))
    return {
        "people": len(shared_people),
        "couples": len(shared_couples),
        "paternal": len(dp),
        "maternal": len(mp),
        "closest": [(c, dc[c], mc[c]) for c in shared_couples[:5]],
    }


def render_collapse(people, couples, data):
    rows = []
    for cid, d, m in data["closest"]:
        c = couples[cid]
        a, b = people.get(c["parent1_pid"], {}), people.get(c["parent2_pid"], {})
        pair = " + ".join(filter(None, [
            f'{e(a.get("name",""))} <span class="ln-yr">{e(a.get("lifespan") or "")}</span>' if a else "",
            f'{e(b.get("name",""))} <span class="ln-yr">{e(b.get("lifespan") or "")}</span>' if b else ""]))
        where = (a.get("birth_place") or b.get("birth_place") or "").split(",")
        where = ", ".join(x.strip() for x in where[:2])
        rows.append(f"        <tr><td>{pair}</td><td>{e(where)}</td>"
                    f'<td class="num">{d}</td><td class="num">{m}</td></tr>')
    cousin = min(data["closest"][0][1], data["closest"][0][2]) - 1
    gap = abs(data["closest"][0][1] - data["closest"][0][2])
    removed = {0: "", 1: ", once removed", 2: ", twice removed"}.get(
        gap, f", {gap} times removed")
    return "\n".join([
        CBEGIN,
        f'  <p class="lead">The two halves of this record are not two families. Walking up '
        f'from each side separately and intersecting the result gives <b>{data["people"]} '
        f'people who are ancestors on both</b>, in <b>{data["couples"]} shared couples</b>. '
        f'The paternal side traces {data["paternal"]} ancestors and the maternal side '
        f'{data["maternal"]}; {data["people"]} of them are the same people.</p>',
        '  <div class="table-wrap">',
        '    <table class="table">',
        '      <caption>Where the two lines were already one · nearest first</caption>',
        '      <thead><tr><th scope="col">Couple</th><th scope="col">From</th>'
        '<th scope="col">Gens up the paternal line</th>'
        '<th scope="col">Gens up the maternal line</th></tr></thead>',
        "      <tbody>",
        "\n".join(rows),
        "      </tbody>",
        "    </table>",
        "  </div>",
        f'  <p class="grade">Nearest convergence: {cousin}th cousins{removed}. Counted '
        f'from the edge graph as it stands, so the figures move when the tree does.</p>',
        CEND])


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
        # Try the entry's own spelling first, then any variant the dedupe
        # dropped, shortest last so the plainest form gets a chance.
        variants = [core] + sorted(entries[core].get("also", []), key=len, reverse=True)
        # Whitespace between the words of a name is flexible, because the prose
        # is hard-wrapped and a name that happens to straddle a line break --
        # "Elijah\n    Haven" -- would otherwise never match. The matched text
        # is kept verbatim so the wrap survives the substitution.
        for variant in variants:
            if pid in done:
                break
            pattern = re.compile(r"(?<![\w-])"
                                 + r"\s+".join(map(re.escape, variant.split()))
                                 + r"(?![\w-])")
            for m in pattern.finditer(page):
                if BEGIN in page[:m.start()] or not _linkable(page, m.start()):
                    continue
                if any(page[m.start():].replace("\n", " ").startswith(x) for x in longer):
                    continue
                page = (page[:m.start()]
                        + f'<a class="lin" href="#lin-{pid}" data-lin="{pid}">{m.group(0)}</a>'
                        + page[m.end():])
                done.add(pid)
                break
    return page, len(done)


def main():
    people, couples, prev, member_of, up = load()
    page = open(PAGE, encoding="utf-8").read()

    stripped = re.sub(r"<svg.*?</svg>", "", page, flags=re.S)
    if BEGIN in stripped:
        stripped = stripped[:stripped.index(BEGIN)]
    # Both generated regions are cut before names are resolved, so a run reads
    # only hand-written text and repeated runs converge.
    stripped = re.sub(re.escape(CBEGIN) + r".*?" + re.escape(CEND), "", stripped, flags=re.S)
    # Collapse whitespace as well as tags. The prose is hard-wrapped, so a name
    # straddling a line break reads as "Elijah\n    Haven" and would fail a
    # plain containment test -- which is how four well-sourced people ended up
    # with no entry at all rather than merely no link.
    page_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", stripped))

    coll = collapse(people, couples, up)
    forced = [pid for cid, _, _ in coll["closest"]
              for pid in (couples[cid]["parent1_pid"], couples[cid]["parent2_pid"]) if pid]
    entries = build_entries(people, couples, prev, member_of, page_text, forced)

    # Remove any previous appendix and previous links, then rebuild both.
    # Consume the trailing blank lines too, or each run adds two more.
    page = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n*", "", page, flags=re.S)
    page = re.sub(r'<a class="lin" href="#lin-[^"]+" data-lin="[^"]+">(.*?)</a>',
                  r"\1", page, flags=re.S)

    # Lambda, not a string: a replacement string would treat backslashes and
    # group references in the generated HTML as escapes.
    block = render_collapse(people, couples, coll)
    page = re.sub(re.escape(CBEGIN) + r".*?" + re.escape(CEND),
                  lambda _: block, page, flags=re.S)
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
    print(f"collapse · {coll['people']} shared ancestors in {coll['couples']} couples")
    print(f"lineages written · {len(entries)} people "
          f"({lin} with a descent, {len(entries) - lin} collateral) · {linked} linked in text")


if __name__ == "__main__":
    main()
