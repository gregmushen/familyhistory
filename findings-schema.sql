-- ══════════════════════════════════════════════════════════════════════════
-- Local research layer for the FamilySearch mirror.
--
-- fs_persons and friends hold what FamilySearch returns. These three tables
-- hold what WE have established: claims, verdicts, the reasoning, and the
-- sources we actually consulted.
--
-- Two things make this more than a notes field:
--   * a source can REFUTE a claim, not only support it
--   * each finding records the person's fingerprint at the time, so a finding
--     self-invalidates when the underlying tree record changes
-- ══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS fs_sources (
  source_id    INTEGER PRIMARY KEY,
  slug         TEXT UNIQUE NOT NULL,
  title        TEXT NOT NULL,
  creator      TEXT,
  year         TEXT,
  kind         TEXT NOT NULL CHECK (kind IN
                 ('book','newspaper','archive','plaque','photograph',
                  'deed','memorial','database','website','manuscript')),
  reliability  TEXT CHECK (reliability IN
                 ('primary','derivative','authored','user-contributed')),
  url          TEXT,
  repository   TEXT,
  retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fs_findings (
  finding_id     INTEGER PRIMARY KEY,
  subject_kind   TEXT NOT NULL CHECK (subject_kind IN
                   ('person','relationship','image','graph')),
  pid            TEXT,
  pid2           TEXT,
  subject_label  TEXT,
  claim          TEXT NOT NULL,
  verdict        TEXT NOT NULL CHECK (verdict IN
                   ('documented','supported','tradition',
                    'unproven','unresolved','refuted')),
  reasoning      TEXT NOT NULL,
  field          TEXT,
  tree_value     TEXT,
  our_value      TEXT,
  narrative_url  TEXT,
  fingerprint    TEXT,
  established_at TEXT NOT NULL,
  superseded_by  INTEGER REFERENCES fs_findings(finding_id)
);

CREATE TABLE IF NOT EXISTS fs_finding_sources (
  finding_id INTEGER NOT NULL REFERENCES fs_findings(finding_id) ON DELETE CASCADE,
  source_id  INTEGER NOT NULL REFERENCES fs_sources(source_id),
  role       TEXT NOT NULL CHECK (role IN ('supports','refutes','conflicts','context')),
  locator    TEXT,
  quote      TEXT,
  PRIMARY KEY (finding_id, source_id, role)
);

CREATE INDEX IF NOT EXISTS idx_findings_pid     ON fs_findings(pid);
CREATE INDEX IF NOT EXISTS idx_findings_verdict ON fs_findings(verdict);
CREATE INDEX IF NOT EXISTS idx_fs_src_finding   ON fs_finding_sources(finding_id);

-- Findings whose underlying tree record has changed since we checked it.
-- The fingerprint is name|lifespan|sourceCount|memoryCount, so a new source
-- attached by a stranger is enough to surface the finding for re-checking.
CREATE VIEW IF NOT EXISTS fs_needs_recheck AS
SELECT f.finding_id, f.pid, f.claim, f.verdict,
       f.fingerprint AS checked_against,
       p.name || '|' || COALESCE(p.lifespan,'') || '|' ||
         COALESCE(p.source_count,0) || '|' || COALESCE(p.memory_count,0) AS current_fingerprint
FROM fs_findings f
JOIN fs_persons p USING (pid)
WHERE f.superseded_by IS NULL
  AND f.fingerprint IS NOT NULL
  AND f.fingerprint <> p.name || '|' || COALESCE(p.lifespan,'') || '|' ||
        COALESCE(p.source_count,0) || '|' || COALESCE(p.memory_count,0);

-- Every point where we knowingly diverge from the tree.
CREATE VIEW IF NOT EXISTS fs_divergences AS
SELECT f.pid, p.name, f.field, f.tree_value, f.our_value, f.verdict, f.claim
FROM fs_findings f LEFT JOIN fs_persons p USING (pid)
WHERE f.superseded_by IS NULL AND f.field IS NOT NULL;

-- A finding with its sources rolled up, for rendering.
CREATE VIEW IF NOT EXISTS fs_findings_full AS
SELECT f.finding_id, f.subject_kind, f.pid, f.subject_label, f.claim, f.verdict,
       f.reasoning, f.narrative_url, f.established_at,
       GROUP_CONCAT(s.title || CASE WHEN fs.role <> 'supports'
                                    THEN ' [' || fs.role || ']' ELSE '' END, ' · ') AS sources
FROM fs_findings f
LEFT JOIN fs_finding_sources fs USING (finding_id)
LEFT JOIN fs_sources s USING (source_id)
WHERE f.superseded_by IS NULL
GROUP BY f.finding_id;
