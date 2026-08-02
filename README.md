# familyhistory

Static site: **Mushen family history — 400 years of American beginnings.**

Five waves of migration into America between 1620 and 1870, traced through
24,263 ancestors in the FamilySearch collaborative tree.

## Deploy (Cloudflare Pages)

| Setting | Value |
| --- | --- |
| Production branch | `main` |
| Framework preset | None |
| Build command | *(none)* |
| Build output directory | `/` |

No build step. `index.html` is served from the repository root.

## Layout

```
index.html            the page
assets/classical.css  design-system tokens, vendored from the Claude Design
                      project `classical-10bd8065`. Source of truth for colour,
                      type, spacing, radius and shadow.
assets/site.css       page implementation of frontend-spec.md
assets/site.js        rail active state, read progress, scroll reveal
assets/img/           archive images
```

Implements `frontend-spec.md` from the Claude Design project. Deviations from
the spec are listed in `NOTES.md`.

## Editorial rules

- No living individual is named, and no birth date or birthplace of a living
  person appears.
- Claims carried by two or more independent archives are marked *documented*;
  everything else is labelled as supported or as family tradition.
- Spellings appear as the clerk wrote them.
