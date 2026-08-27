# Phase 1 Extension Review Status

- Status date: `2026-08-27 21:46 Asia/Seoul`
- Live export status: `PASS`
- Live review-pack generation status: `GENERATED_AND_VERIFIED`
- Planned deterministic seed: `20260823`
- Planned sample size: `20` per comparison group, `100` total
- Human review status: `PENDING`; valid human labels are `0 / 100`.
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

## Deterministic sample measurements

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

Generated-file hashes:

| File | Bytes | SHA-256 |
|---|---:|---|
| `README.md` | 758 | `607E6A0F345D02201F77728F93638D693C586F73C7C3589BE0922BC9698E9B9D` |
| `review_labels.csv` | 3,313 | `3591F5006C09F9D75FBF95E3401286E5F9223028F93A6CA1ABC4B8A40D58AF09` |
| `samples.csv` | 119,375 | `BCF1702FD7C1D85B7B676FA66F752FC04853FAC3AB9C9A2DB48D4353534B774C` |

The pack contains exactly these three files. Its headers match the frozen
contracts, all 100 label rows correspond to the 100 sample rows, every human
label field is blank, and no actual key value, URL, C003 envelope, or prohibited
metadata was detected.

## Pending human review

The data and pack gates are complete. The following still require a person:

- advertising-risk score from 1 through 5 for every row;
- functional-diversity score from 1 through 5 for every row;
- implementation-feasibility score from 1 through 5 for every row;
- nonblank reviewer and ISO 8601 reviewed-at value for every row;
- review of ambiguous mappings before trusting any aggregate recommendation.

No extension choice may be finalized before all 100 samples receive valid human
labels. The seed and mapping rules make sampling reproducible; they do not replace
human review or prove clinical equivalence.

## Reproduction commands

Run these commands in **CMD** only when reproducing the local artifacts. Do not
paste the key into a tracked file or command output. The canonical variable name
is `FOOD_SAFETY_API_KEY`.

```cmd
set FOOD_SAFETY_API_KEY=your-local-key
.venv\Scripts\python.exe scripts\audit_c003.py --export-products data\c003-products.jsonl
.venv\Scripts\python.exe scripts\build_extension_review.py --input data\c003-products.jsonl --output-dir build\extension-review --seed 20260823
```

The current next action is to fill `build/extension-review/review_labels.csv`
using `build/extension-review/samples.csv` as the source sheet. Collect all 100
human labels before making any extension recommendation or final choice.
