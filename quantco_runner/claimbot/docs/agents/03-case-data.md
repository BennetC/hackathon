# 03 Case data

Location (local, encrypted): the Drive folder "[PUBLIC] Road to Start HACK/Cases/",
`case_000.zip` … `case_100.zip` (101 files). Copy them into a git-ignored `data/cases/`.
Do **not** commit case files or decrypted contents.

## Archive contents (from zip metadata; contents still encrypted)

| File | Present | Size (uncompressed) | Notes |
|---|---|---|---|
| `policy.txt` | all | min 0.9 KB (case 0), median ~56 KB, max ~75 KB | Full insurance terms (likely German). ~14k tokens typical. |
| `description.txt` | all | 0.2–4 KB, median ~0.8 KB | Damage report |
| `invoices.pdf` | all | 14–75 KB, median ~30 KB | Line items with quantity and unit, **no prices**. Probably text-based; verify (else OCR). |
| photos | 100 of 101 | up to 31 MB total | Names vary: `photo.jpg` (76), `photo.png` (15), `photo.jpeg` (2), `photo1.png`+`photo2.png` (5), `photo1..3.png` (1), `photo1.jpg`+`photo2.jpg` (1); `case_045` has none. **Glob `photo*`**; the docs say `images.png`, but that is wrong. |

Encryption: AES (zip method 99) on every file.

## Policy reuse

Grouping by exact `policy.txt` byte size: ~50 distinct sizes across 101 cases, with
groups of 2–5 cases. For example, sizes 41425 → cases 001, 009, 015, 017, 019; 74609 → 002, 006, 022, 033.
→ Cache parsed policies by **content hash** (coverage list, exclusions, deductibles,
sub-limits) so repeated policies skip the expensive parse. Size equality is only a hint;
key the cache on the hash.

## What to extract per case

- **From the policy:** insured perils (e.g. tap water / Leitungswasser, storm, fire, glass, motor), covered object classes (building vs contents), explicit exclusions, sub-limits, deductible (*Selbstbeteiligung*), whether costs like drying, leak detection, or tear-out and restoration (*Nebenkosten*) are covered.
- **From the description:** cause, date, affected rooms and items, extent.
- **From the invoice:** for each line: `index`, description, quantity, unit (m², Std., Stk., pauschal, …), and any VAT rate stated. Lines are numbered by position; confirm the numbering convention against case 0.
- **From photos:** consistency with the story (location, extent). Optional signal; photos are large, so downscale before any vision call.

## Unknowns to confirm on case 0

Invoice language and layout, VAT rate (assume 19 % DE unless stated), line numbering,
and whether invoices contain subtotals or headers that must be skipped as non-lines.
