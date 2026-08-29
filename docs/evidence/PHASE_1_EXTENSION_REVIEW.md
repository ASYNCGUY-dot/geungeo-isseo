# Phase 1 Extension Review Status

- Status date: `2026-08-30 Asia/Seoul`
- Live export status: `PASS`
- Product review v2 pack status: `GENERATED_AND_VERIFIED`
- Planned deterministic seed: `20260823`
- Planned sample size: `20` per comparison group, `100` total
- Product mapping/function-text human review status: `COMPLETE`; valid human labels are `100 / 100`, pending labels are `0 / 100`.
- Mapping review: `99 correct / 1 incorrect / 0 uncertain`; the one error is `red_ginseng` report `20160012278100` with reason `alias_collision`.
- Function-text review: `usable 100 / 100`. This records usable official function text for row-level review; it does not prove an ingredient caused the function.
- Completed labels SHA-256: `A00B3C1A038DBFD06484A89A6C1B41AAA63837D3BD87FAC29E2AF5DF0E011CC1`
- Functional-role review A: not yet built.
- Advertising evidence status: `NOT_MEASURED`
- Extension recommendation status: `BLOCKED`; `finalized=false`
- Finalized extension ingredients: `none`

## Data boundary

The local export path is `data/c003-products.jsonl`. Git ignores only this exact
generated dataset path; the rest of `data/` remains eligible for intentionally
redacted fixtures. Generated review files remain ignored under the existing
`build/` rule. Export writes are staged under `build/c003-export/`, which is on
the same project volume and already ignored by that rule, before `os.replace`
atomically replaces the final ignored JSONL path. Normal failures remove their
temporary file and clean the staging directory when it is empty; crash remnants
remain ignored under `build/`.

The historical v1 pack remains at `build/extension-review/`. The current v2
pack is `build/extension-review-v2/`. Both are ignored generated artifacts; v1
is retained for audit history and must not be treated as the current review
contract.

Each exported JSONL object is limited to these six fields:

1. `report_no`
2. `name`
3. `company`
4. `primary_function`
5. `raw_materials`
6. `intake_method`

The export does not serialize the API key, C003 response envelope, source URL,
`source_id`, retrieval timestamp, or any other C003 field.

## Live export measurements

- Retrieval timestamp: `2026-08-27T12:42:29.050550+00:00`
- Source: `Food Safety Korea C003`
- API result: `INFO-000`
- API total / fetched / JSONL rows / loader records: `45,907 / 45,907 / 45,907 / 45,907`
- Unique / duplicate report numbers: `45,907 / 0`
- Export size: `43,799,547` bytes
- Export SHA-256: `CF0D58B478408448F1D9FC0C2A5EB22E3E08055675072C8B863CD6E112703B7E`
- Schema: every row has exactly `report_no`, `name`, `company`,
  `primary_function`, `raw_materials`, and `intake_method`
- Missing values: product name `0`, company `0`, primary function `100`, raw
  materials `1`, intake method `409`
- Actual key value, URL text, API envelope, and prohibited serialized metadata:
  none detected

Full-dataset mapping states under `ingredient-map-v1` are:

| Mapping state | Count | Rate |
|---|---:|---:|
| `verified_mapping` | 20,740 | 45.178295% |
| `ambiguous` | 25,166 | 54.819526% |
| `unverifiable` | 1 | 0.002178% |

These mapping states measure the current narrow alias rules. They do not prove
clinical equivalence or product efficacy.

## Comparison-group pool measurements

| Group | Pool | Six-field complete | Complete rate | Verified | Verified rate | Ambiguous | Ambiguous rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| `milk_thistle` | 2,329 | 2,318 | 99.5277% | 548 | 23.5294% | 1,781 | 76.4706% |
| `vitamin_d` | 11,680 | 11,639 | 99.6490% | 2,574 | 22.0377% | 9,106 | 77.9623% |
| `red_ginseng` | 6,289 | 6,139 | 97.6149% | 4,497 | 71.5058% | 1,792 | 28.4942% |
| `coenzyme_q10` | 1,840 | 1,835 | 99.7283% | 611 | 33.2065% | 1,229 | 66.7935% |
| `magnesium` | 18,089 | 18,041 | 99.7346% | 7,514 | 41.5391% | 10,575 | 58.4609% |

`unverifiable` is zero inside these pools because a product enters a group pool
only when an explicit reviewed alias assigns that group. The full-dataset table
above retains the one globally unverifiable record.

## Historical v1 deterministic sample measurements

This section records the preserved v1 artifact. Its 1-through-5 advertising
risk, functional diversity, implementation feasibility, and recommendation-only
contract is superseded by v2 and is not an authorized input to the current
review.

All sample rows use seed `20260823`, all 100 group/report pairs are unique, and
the 100 sampled report numbers are globally unique. Every sampled row has all six
fields populated and matches the exported source row and recomputed mapping.

| Group | Sample | Unique | Verified | Ambiguous | Six-field complete |
|---|---:|---:|---:|---:|---:|
| `milk_thistle` | 20 | 20 | 4 | 16 | 20 |
| `vitamin_d` | 20 | 20 | 6 | 14 | 20 |
| `red_ginseng` | 20 | 20 | 10 | 10 | 20 |
| `coenzyme_q10` | 20 | 20 | 9 | 11 | 20 |
| `magnesium` | 20 | 20 | 4 | 16 | 20 |

Historical v1 generated-file hashes:

| File | Bytes | SHA-256 |
|---|---:|---|
| `README.md` | 758 | `607E6A0F345D02201F77728F93638D693C586F73C7C3589BE0922BC9698E9B9D` |
| `review_labels.csv` | 3,313 | `3591F5006C09F9D75FBF95E3401286E5F9223028F93A6CA1ABC4B8A40D58AF09` |
| `samples.csv` | 119,375 | `BCF1702FD7C1D85B7B676FA66F752FC04853FAC3AB9C9A2DB48D4353534B774C` |

The pack contains exactly these three files. Its headers match the frozen
contracts, all 100 label rows correspond to the 100 sample rows, every human
label field is blank, and no actual key value, URL, C003 envelope, or prohibited
metadata was detected.

## Product review v2 evidence — 2026-08-28

The current v2 pack was generated offline from the verified local six-field
export with seed `20260823`. No API or network call was used. It contains
exactly four files:

| File | Bytes | SHA-256 |
|---|---:|---|
| `README.md` | 743 | `4F5F610A64A7E90DDED10E3C468D9E330CE2D18092315A0DB0BABBEAB5BC4238` |
| `manifest.json` | 471 | `0E3086DF9F2A8895D7845E8B24D00DBE18A43CEEE9C6DC92CBE9095FD873D442` |
| `product_review_labels.csv` (2026-08-28 당시 빈 템플릿) | 3,499 | `DC65DBC164CDB135C8C0B0FF7688CEB6F3766E92B6D47BBC0C55CB9FEA350CC8` |
| `samples.csv` | 119,375 | `BCF1702FD7C1D85B7B676FA66F752FC04853FAC3AB9C9A2DB48D4353534B774C` |

The manifest was parsed and revalidated with these observed values:

- contract version: `c003-product-review-v2`
- seed: `20260823`
- sample count: `100`
- group counts: `milk_thistle=20`, `vitamin_d=20`, `red_ginseng=20`,
  `coenzyme_q10=20`, `magnesium=20`
- mapping rule versions: `ingredient-map-v1`
- source export SHA-256:
  `CF0D58B478408448F1D9FC0C2A5EB22E3E08055675072C8B863CD6E112703B7E`
- samples SHA-256:
  `BCF1702FD7C1D85B7B676FA66F752FC04853FAC3AB9C9A2DB48D4353534B774C`

The v2 samples hash is byte-for-byte identical to the preserved v1 samples
hash. The v1 files remain present with their recorded hashes unchanged.

2026-08-28 당시 빈 템플릿의 v2 validator는 process exit `2`를 반환했고, 다음은 그 과거
결과다:

- status `PENDING`
- valid labels `0 / 100`
- pending labels `100 / 100`
- summary `null`
- advertising evidence `NOT_MEASURED`
- extension recommendation `BLOCKED`
- `finalized=false`

2026-08-28 당시 빈 템플릿의 labels file은 정확히 100행이고 nonblank human-review field가
0개였다.
Count-only scans found zero high-confidence key/token patterns, URLs, C003
envelope fields, and prohibited metadata. One actual local key value from the
main checkout `.env` was compared in memory without printing it; occurrences
inside the four v2 files were `0`. Neither v1 nor v2 appears in `git status`, and
`git ls-files -- data build` remains empty.

The v2 validator checks the manifest, hashes, exact headers, five-by-twenty
composition, composite keys, source row identity, recomputed deterministic
mapping, complete human rows, spreadsheet formula prefixes, timezone-aware
timestamps, and a 24-hour future tolerance. `COMPLETE` produces only review
quality metrics and 95% Wilson intervals. It does not call legacy extension
scoring or produce an extension candidate.

## Completed v2 human review and remaining gates

The export and v2 pack integrity gates are complete, and all 100 rows now have
valid human review fields. The current validator returned process exit `0` with
`COMPLETE`, valid labels `100 / 100`, pending labels `0 / 100`, mapping `99
correct / 1 incorrect / 0 uncertain`, and function-text `usable 100 / 100`.
The single incorrect mapping is `red_ginseng` report `20160012278100`, marked
`alias_collision`; it is preserved as an observed review error, not rewritten
as a correct mapping.

The completed label file SHA-256 is
`A00B3C1A038DBFD06484A89A6C1B41AAA63837D3BD87FAC29E2AF5DF0E011CC1`.
`function_text_status=usable` means only that the row's official function text
is usable for this review. It does not establish that an ingredient caused the
function, clinical equivalence, product efficacy, or advertising compliance.

Functional-role review A is not yet built. No extension choice may be finalized
before that separate gate and a separate official advertising-evidence gate are
complete. Advertising evidence remains `NOT_MEASURED`; extension recommendation
remains `BLOCKED`; `finalized=false`. The seed and mapping rules make sampling
reproducible; they do not replace the remaining gates.

## Reproduction commands

The verified export already exists locally, so rebuilding and validating the v2
pack requires no API key or network call:

```cmd
.venv\Scripts\python.exe scripts\build_extension_review.py --input data\c003-products.jsonl --output-dir build\extension-review-v2 --seed 20260823
.venv\Scripts\python.exe scripts\validate_product_review.py --pack-dir build\extension-review-v2 --source-export data\c003-products.jsonl
```

The current next action is to build functional-role review A using the completed
`build/extension-review-v2/product_review_labels.csv` and its evidence sheet.
Do not fill the historical v1 numeric score file. Do not make an extension
recommendation or final choice while advertising evidence remains unmeasured,
functional-role review A remains unbuilt, and the status remains `BLOCKED`.
