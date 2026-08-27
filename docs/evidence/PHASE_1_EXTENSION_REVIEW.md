# Phase 1 Extension Review Status

- Status date: `2026-08-27 Asia/Seoul`
- Live export status: `BLOCKED`
- Live review-pack generation status: `NOT RUN`
- Reason: three C003 attempts at approximately `11:09-11:10 KST` all returned
  official API `ERROR-503` with the daytime congestion notice.
- Planned deterministic seed: `20260823`
- Planned sample size: `20` per comparison group, `100` total
- Human review status: `PENDING`; no live review pack was available for labeling.
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

## Measurements

No current C003 dataset was exported in this run, so current exported-record
counts, uniqueness, field completeness, comparison-group pool sizes, and mapping
state counts or rates are `NOT MEASURED`.

The key was connected only inside the request subprocess and neither its value nor
the key-bearing request URL was printed. The three service errors are recorded in
[`C003_LIVE_ATTEMPT.md`](C003_LIVE_ATTEMPT.md). They do not prove successful key
authorization or current dataset completeness.

The dated Phase 0 report at `docs/evidence/C003_COVERAGE_REPORT.md` records a
separate `2026-08-22T15:27:28.041740+00:00` measurement: 45,720 fetched records,
45,720 unique report numbers, no duplicate report numbers, and completeness of
100.00% for product name, 100.00% for company, 99.78% for primary function,
100.00% for raw materials after two-decimal rounding, and 99.11% for intake
method. Those historical measurements are not presented as a current Task 8
export or extension-review result.

## Pending comparison review

The planned comparison groups are `milk_thistle`, `vitamin_d`, `red_ginseng`,
`coenzyme_q10`, and `magnesium`. For each group, the offline generator must
produce 20 unique official report numbers. The following remain pending until a
live export and review pack exist:

- measured pool and sample counts for every comparison group;
- measured `verified_mapping`, `ambiguous`, and `unverifiable` mapping states
  and rates;
- completeness of the six exported fields in the selected samples;
- inspection for unexpected envelope, key, URL, or user-data content;
- all 100 human labels for advertising risk, functional diversity, and
  implementation feasibility.

No extension choice may be finalized before all 100 samples receive valid human
labels. The seed and mapping rules make sampling reproducible; they do not replace
human review or prove clinical equivalence.

## Authorized operator commands

Retry outside the API's stated daytime congestion window. Run these commands in
**CMD** with a locally supplied key. Do not paste the key into a tracked file or
command output. The canonical variable name is `FOOD_SAFETY_API_KEY`; the local
untracked file currently uses the legacy name `FOODSAFETY_API_KEY` and should be
renamed locally before the next run.

```cmd
set FOOD_SAFETY_API_KEY=your-local-key
.venv\Scripts\python.exe scripts\audit_c003.py --export-products data\c003-products.jsonl
.venv\Scripts\python.exe scripts\build_extension_review.py --input data\c003-products.jsonl --output-dir build\extension-review --seed 20260823
```

After generation, inspect all five groups for 20 unique report numbers, record
the measured completeness and mapping states here, and collect all 100 human
labels before making any extension recommendation or final choice.
