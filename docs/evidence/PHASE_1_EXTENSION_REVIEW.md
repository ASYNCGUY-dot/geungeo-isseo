# Phase 1 Extension Review Status

- Status date: `2026-09-27 Asia/Seoul`
- Live export status: `PASS`
- Product review v2 pack status: `GENERATED_AND_VERIFIED`
- Planned deterministic seed: `20260823`
- Planned sample size: `20` per comparison group, `100` total
- Product mapping/function-text human review status: `COMPLETE`; valid human labels are `100 / 100`, pending labels are `0 / 100`.
- Mapping review: `99 correct / 1 incorrect / 0 uncertain`; the one error is `red_ginseng` report `20160012278100` with reason `alias_collision`.
- Function-text review: `usable 100 / 100`. This records usable official function text for row-level review; it does not prove an ingredient caused the function.
- Completed labels SHA-256: `A00B3C1A038DBFD06484A89A6C1B41AAA63837D3BD87FAC29E2AF5DF0E011CC1`
- Functional-role review A: `COMPLETE` on 2026-09-27 using user-approved **AI proxy labels** (valid `275 / 275`, issues `0`, exit `0`). `ROLE_ELIGIBLE`: vitamin_d, coenzyme_q10, magnesium; `ROLE_INSUFFICIENT`: milk_thistle, red_ginseng. Human accuracy is unmeasured. See [AI-proxy closure](FUNCTIONAL_ROLE_GATE_AI_PROXY_2026-09-27.md) and `functional-role-summary-v1-ai-proxy.json`.
- Advertising evidence status: `NOT_MEASURED`
- Extension recommendation status: `BLOCKED`; `finalized=false`
- Finalized extension ingredients: `none`

## 2026-09-27 A closed with AI proxy labels; B/C deferred

- User decision: skip human review, close A with the completed AI review as proxy labels, and build the core
  three-ingredient MVP before extension selection. The 269 AI rows were written into the operating 9/23 pack labels;
  the six earlier rows are unchanged. Real validator: COMPLETE, valid 275, pending 0, issues 0, exit 0.
- Redacted summary `functional-role-summary-v1-ai-proxy.json` (SHA-256 `2F235A7C…D04A02B`) contains no product text or reviewer.
  vitamin_d, coenzyme_q10, magnesium are ROLE_ELIGIBLE (35/35 positive agreement, Wilson lower 0.901);
  milk_thistle (4 unresolved positives) and red_ginseng (17) are ROLE_INSUFFICIENT.
- "Eligible" here means machine positives agreed with the AI proxy, not human-verified accuracy.
  B NOT_MEASURED, C BLOCKED, finalized=false, no extension ingredient selected.

## 2026-09-27 AI review completion

- [Completion record](FUNCTIONAL_ROLE_AI_REVIEW_2026-09-27.md): the four remaining groups (214 rows) were fully
  re-reviewed by Claude Code (`claude-opus-5-5`), and all 55 magnesium rows were cross-checked by the same model.
  Content changes: 0 of 269. Review files keep their 9/23 hashes. This is a non-blind AI revision audit, not human review.
- Python structure check `validate-2026-09-27.py`: PASS_STRUCTURE_ONLY, 5 groups completion-confirmed, 0 warnings, exit 0.
- Operating validator unchanged: PENDING, valid 6, pending 269, issues 0, exit 2. The 9/23 rule freshness boundary is
  `2026-09-30T15:02:04+09:00`. Human accuracy and A eligibility remain unmeasured; B NOT_MEASURED, C BLOCKED, finalized=false.

## 2026-09-23 AI draft and source-renewal checkpoint

- [Current AI handoff](FUNCTIONAL_ROLE_AI_REVIEW_2026-09-23.md): 269 stored draft rows, 1,614 exact
  source fields, 490 literal excerpts, 13 protected hashes preserved; two targeted corrections.
  Magnesium has a saved complete55-row revision record; four groups/214rows remain unfinalized after
  usage-limit interruption. Structure checks do not establish semantic or human accuracy.
- [Renewal evidence](FUNCTIONAL_ROLE_RECHECK_2026-09-23.md): official ZIP unchanged; separate
  `reverified-2026-09-23` rules/pack; actual PENDING valid6/pending269/issues0/exit2/summary null.
  Old rules/packs remain intact. No new AI draft was copied into human_verdict.
- Today full suite609passed/293.72s, coverage97.22%, Ruff clean. No production code/test changes.
- Approval already covers269 separate AI references. Human evaluation and A eligibility remain
  unmeasured; B NOT_MEASURED, C BLOCKED, finalized=false.

## 2026-09-14 source renewal and approved AI-label checkpoint

- See [renewal evidence and current operating command](FUNCTIONAL_ROLE_RECHECK_2026-09-14.md)
  and [AI provenance record](functional-role-ai-review-provenance-2026-09-14.json).
- Official source checked at `2026-09-14T15:13:50+09:00`; downloaded official ZIP matches prior
  SHA-256. Only five `verified_current_at` values changed in a separate registry copy.
- New current pack: `build/functional-role-review-v1-reverified-2026-09-14/`.
  Original pack, rule registry, AI response and v2 labels remain unchanged.
  All 275 samples and migrated labels are byte-identical to the originals.
- Real validator: PENDING, valid 6, pending 269, no issues, exit 2, summary null.
  Pending by group: milk_thistle 50, vitamin_d 55, red_ginseng 54, coenzyme_q10 55, magnesium 55.
- AI provenance remains `CLAUDE-OPUS-5-AI`. User approval is not independent human/expert
  ground truth. Mixed-source metrics must not be reported as human accuracy.
- Cases 1 and 5 remain unresolved code/AI disagreements; no decision-rule relaxation.
  A eligibility remains unmeasured; B NOT_MEASURED, C BLOCKED, finalized false.

## 2026-09-10 human-review handoff checkpoint

- Real validator rerun completed at `2026-09-10T23:34:01+09:00`: `PENDING`, expected 275,
  valid 1, pending 274, issues 0, exit 2, summary null. The valid row is inherited mapping-error exclusion.
- Added [user handoff](../USER_REVIEW_HANDOFF.md) and an ignored, unfilled first-batch response
  sheet at `build/functional-role-review-guides/batch-001-response.md`, outside the four-file pack.
- Per-group pending rows: milk_thistle 55, vitamin_d 55, red_ginseng 54, coenzyme_q10 55,
  magnesium 55. No product verdict, evidence excerpt, reviewer or review time was filled.
- Rules, role manifest/samples/labels and v2 labels retain the previously recorded SHA-256 values.
  No source, rule, protected pack, code, test or COMPLETE summary was changed/generated.
- The existing 609-test/97.22% result is the 2026-09-09 run, not a new full-suite run for these docs.
- Last recorded official-source check remains `2026-09-04T17:31:53+09:00`; no official website
  recheck was performed in this checkpoint. More than seven days requires actual re-verification,
  not a date/hash edit. This is an internal freshness rule, not a legal expiry or a human-review deadline.
- A awaits product-level human input. B is `NOT_MEASURED`, C is `BLOCKED`, finalized is false.

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

- 2026-08-28 당시 status `PENDING`
- 2026-08-28 당시 valid labels `0 / 100`
- 2026-08-28 당시 pending labels `100 / 100`
- 2026-08-28 당시 summary `null`
- 2026-08-28 당시 advertising evidence `NOT_MEASURED`
- 2026-08-28 당시 extension recommendation `BLOCKED`
- 2026-08-28 당시 `finalized=false`

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

Functional-role review A is built and awaiting product-level human review. No extension choice may be finalized
before that separate gate and a separate official advertising-evidence gate are
complete. Advertising evidence remains `NOT_MEASURED`; extension recommendation
remains `BLOCKED`; `finalized=false`. The seed and mapping rules make sampling
reproducible; they do not replace the remaining gates.

## Functional-role rule and pack evidence — 2026-09-04 / rechecked 2026-09-07

The rule registry was committed as `7678890`. Human source review was reported by
the user with distinct aliases `extracted_by=CHOI`, `reviewed_by=DOHA`, and fresh
confirmation time `2026-09-04T17:28:58+09:00`. This is provenance for the five rules;
it does not certify the newly generated product-level role labels or professional credentials.

- Source ID: `MFDS-NOTICE-2026-43-FULL-TEXT`
- Notice and generally effective date: `제2026-43호 / 2026-06-11`
- [Official consolidated text](https://www.mfds.go.kr/brd/m_211/view.do?seq=14973)
- [Official amendment](https://www.mfds.go.kr/brd/m_207/view.do?seq=15173)
- Official retrieval / current-status verification: `2026-09-04T17:31:53+09:00`
- Source ZIP: `3,524,589` bytes; ZIP signature `50-4B-03-04`; three HWPX entries
- Source ZIP SHA-256: `3D25C54F8248204C75E02F889C1EE4ADC3BC3FA2188ED91DA06DA33402AFEBFB`
- At the above retrieval time, a fresh official download and the preserved attachment had identical bytes.
- Registry contract: `functional-role-rules-v1`; rule version: `functional-role-rule-v1`
- Magnesium requires explicit target wording; the other four rules use conservative function phrases.
  Real C003 row `200400151074` remains `unverifiable/combination_linkage_ambiguous` for magnesium.
- The registry loader rejects verification older than seven days. The current timestamp reaches
  that boundary at `2026-09-11T17:31:53+09:00`. A later run must perform an actual source recheck;
  dates must not be silently rewritten inside hash-bound inputs.

The pack was generated once at `2026-09-04T08:46:00.200585Z` (17:46 KST),
using seed `20260823`, mapping rule `ingredient-map-v1`, and the completed v2 input.
It has 275 sample rows, 275 label rows, and 275 distinct `(group, report_no)` keys.
All first 100 keys, row order, and six source fields match the v2 samples exactly.
The completed v2 label hash was checked unchanged before and after generation.

| Group | Original v2 | Inherited error | Replacement | Evaluable general | Machine-positive pool | Positive sample | Unique rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| milk_thistle | 20 | 0 | 0 | 20 | 1,268 | 35 | 55 |
| vitamin_d | 20 | 0 | 0 | 20 | 1,360 | 35 | 55 |
| red_ginseng | 20 | 1 | 1 | 20 | 2,589 | 35 | 55 |
| coenzyme_q10 | 20 | 0 | 0 | 20 | 667 | 35 | 55 |
| magnesium | 20 | 0 | 0 | 20 | 2,316 | 35 | 55 |

General and positive audit membership can overlap, so their sizes are not additive.
The machine-positive pool is a sampling population, not a count of human-confirmed products.
The red-ginseng mapping error stays excluded; its replacement does not erase the original.

Bound input SHA-256 values:

| Input | SHA-256 |
|---|---|
| Source export | `CF0D58B478408448F1D9FC0C2A5EB22E3E08055675072C8B863CD6E112703B7E` |
| v2 manifest | `0E3086DF9F2A8895D7845E8B24D00DBE18A43CEEE9C6DC92CBE9095FD873D442` |
| v2 samples | `BCF1702FD7C1D85B7B676FA66F752FC04853FAC3AB9C9A2DB48D4353534B774C` |
| Completed v2 labels | `A00B3C1A038DBFD06484A89A6C1B41AAA63837D3BD87FAC29E2AF5DF0E011CC1` |
| Rule registry | `E8611F98A41885D65B79AA02ECBDB74A3937F95EB4BE2CCF3C2925D1A0966E7D` |

The ignored `build/functional-role-review-v1/` directory contains exactly
`README.md`, `manifest.json`, `samples.csv`, and `functional_role_labels.csv`.
The following hashes were checked again on 2026-09-07:

| File | Bytes | SHA-256 |
|---|---:|---|
| manifest.json | 2,369 | `FE6186AA2B0454BF24406A80B10198080800989D53BE2BFB794AA1337BEAA538` |
| samples.csv | 384,153 | `2A5A2554C5B0A5C0FB289E902CC210274A3B99294E8C3779A9CB309B233EDF25` |
| functional_role_labels.csv | 15,616 | `B98389AD79ED119B14FA5F1B42420239A56EEF24B757A775C07775F8E44CDFE8` |

On 2026-09-07 the actual validator returned `PENDING`, expected labels `275`,
valid `1`, pending `274`, issues `[]`, summary `null`, process exit `2`.
The one valid row is the inherited mapping-error exclusion. No new human verdict was fabricated.
Role eligibility and real accuracy are unmeasured. Advertising evidence is `NOT_MEASURED`,
recommendation `BLOCKED`, and `finalized=false`.

2026-09-04 verification: 506 full tests passed, 63 functional-rule tests passed,
163 role-review tests passed; total coverage 94% (2,485 statements, 147 missed).
At that time, the plan's 97% coverage target was not met. This historical code-coverage
result must not be confused with measured classification accuracy.

On 2026-09-07 the first rerun found one test-only clock failure: the CLI subprocess
used the actual clock while its synthetic rule fixture was fixed at 2026-08-30.
The real seven-day freshness gate correctly rejected it. CLI tests now use a
temporary synthetic registry relative to execution time and explicitly cover an eight-day-old
registry rejection. The production gate and real registry were not changed.

After that test-only fix, the 2026-09-07 full rerun returned `507 passed in 236.45s`,
coverage `94%` (2,485 statements / 147 missed, 94.08%), Ruff clean, and
`git diff --check` clean. The three CLI regression cases also passed.
Pack revalidation, unchanged-label hashes, all 275 unique keys, the first 100 v2 rows,
and verbatim source text for the first five reviewer-guide rows were checked directly.

## Malformed-input hardening — 2026-09-09

A public-validator regression reproduced an unhandled `TypeError` when rule JSON
contained a numeric source identifier, a null reviewer, a null phrase list, or a
non-text phrase. Four integration cases and 23 rule-model cases failed before
the fix. The two rule input validators now raise `ValueError`, which Pydantic
wraps in the existing redacted `ValidationError` contract. The review validator
therefore returns `INVALID/RULES_INVALID` instead of crashing. Normal rule
matching, source freshness, and all recommendation restrictions are unchanged.

Added offline tests also exercise permission failures, invalid encoding, oversized
documents, malformed CSV, source duplicates, label/provenance mismatches,
recomputed hashes over corrupted prerequisites, and partial-output cleanup.
All filesystem fault injection is limited to temporary synthetic fixtures.
No real human review identities or product verdicts are generated by these tests.

An independent review identified a test-only false-green risk: the malformed-rule
subprocess fixture was already stale, and freshness rejection could also supply
`RULES_INVALID`. Adding an uncorrupted baseline assertion first reproduced that
problem (`1 failed`, actual exit `3` instead of expected `2`). The fixture helper
now accepts an explicit synthetic rule path and generation time while preserving
fixed-clock defaults for other tests. The CLI test constructs and hash-binds current
synthetic rules, checks an uncorrupted `PENDING`/exit `2` result with no issues, then
corrupts the source identifier and requires `INVALID`/exit `3`, no traceback, no
rejected value, and no published summary. The focused rerun passed (`1 passed`).
The independent read-only re-review marked its P2 finding resolved, with no
remaining actionable introduced issue in that follow-up. This is code review,
not human product-role review or release approval.

Final clean verification after that follow-up: `609 passed in 311.60s`, exit `0`.
Statement coverage is `2,416 / 2,485 = 97.22334004024145%`, with `69` missed and
`0` excluded lines; `--cov-fail-under=97` passed. This closes the previously unmet
engineering-coverage target, not the product-role accuracy or human-review gate.
The suite has 102 more cases than the 507-case baseline. Ruff and changed-file
format checks passed; `git diff --check` found no whitespace errors, and the
high-confidence secret-pattern scan found zero matching changed files.

Reopened local reports are preserved under ignored `build/`:
`coverage-2026-09-09.json` and `test-results-2026-09-09.xml`.

The real existing pack was revalidated on 2026-09-09: `PENDING`, expected `275`,
valid `1`, pending `274`, issues `[]`, summary `null`, exit `2`. The rule registry,
v2 labels, role manifest, role samples, and role label hashes still match the
values recorded above. The source itself was not fetched again on this date.

## Reproduction and human review

Use existing files; do not regenerate a populated v2 or role pack. No API key is needed:

```powershell
.venv\Scripts\python.exe scripts\validate_functional_role_review.py --pack-dir build\functional-role-review-v1 --source-export data\c003-products.jsonl --product-review-pack build\extension-review-v2 --rules data\reference\functional-role-rules-v1.json
$roleValidatorExit = $LASTEXITCODE
$roleValidatorExit
```

Capture the Python exit code immediately: an outer PowerShell process can otherwise report
generic failure `1` for native exit `2`. Expected state mappings are `0=COMPLETE`,
`2=PENDING`, and `3=INVALID`.

The first five pending rows, in existing sample order, are presented in
`build/functional-role-review-guides/batch-001.md`, outside the protected four-file pack.
It contains exact source text and a response format; it does not prefill human verdicts.

Keep `group`, `report_no`, `audit_round`, `machine_verdict`, and `rule_version` fixed.
Human input fields are the following seven fields (the plan prose says six but enumerates seven):
`human_verdict`, `reason_code`, `evidence_field`, `evidence_excerpt`, `review_note`,
`reviewer`, and `reviewed_at_iso8601`.
The reviewer must check the literal material/function text and corresponding rule.
Use `uncertain` when linkage cannot be established. Candidate excerpts are allowed;
human confirmation is required before writing completed labels.
Validate after each batch. Publish `docs/evidence/functional-role-summary-v1.json` only
after the validator returns `COMPLETE`.
