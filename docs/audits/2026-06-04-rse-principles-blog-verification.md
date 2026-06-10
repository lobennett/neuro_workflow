# RSE-PRINCIPLES.md — blog-verification audit (2026-06-04)

Audit trail for the refinement of `docs/RSE-PRINCIPLES.md` against the live
source blog, [russpoldrack.substack.com](https://russpoldrack.substack.com).

## Goal

Confirm that every criterion in the rubric (a) cites a post that actually
exists and (b) accurately states what that post says, then close coverage gaps
with verified missing principles. The rubric is used as a citable standard in
code review/onboarding, so each criterion must be faithful to its source.

## Method

A multi-agent verification workflow (127 subagents):

1. **Enumerate** the real corpus via `sitemap.xml` (69 `/p/` posts) + web search.
2. **Read** each of the 40 cited posts, extracting prescriptive claims with
   verbatim quotes.
3. **Audit** all 112 criteria, section by section, against the extracted claims
   — classifying each as supported / miscited / unsupported / redundant, and
   proposing missing principles + rephrasings.
4. **Adversarially verify** every proposed change by an independent agent
   re-fetching the cited post (default-to-reject); 60 of 75 proposed changes
   upheld, 15 rejected and dropped.

## Findings

| Check | Result |
|---|---|
| Cited slugs that are real posts | **40/40** (zero fabricated) |
| Criteria with no blog support | **0** |
| Redundant criteria | **0** |
| Miscitations (wrong/weak citation) | **5** (ST-6, TE-2, DM-8, DM-12, RF-9) |
| Overstatement rephrasings | ~20 |
| Real RSE posts not cited (coverage gaps) | 10 |
| Verified missing principles added | 44 (deduped from 56 upheld) |
| Proposed changes rejected by verifier | 15 (incl. all 3 Documentation additions) |

## Changes applied

- **Citations corrected.** Dropped citations a post doesn't support (e.g. ST-6's
  `computational-notebooks`); re-sourced RF-9 to `optimizing-the-testing-workflow`
  + `test-driven-development-and-ai-assisted`.
- **Overstatements trimmed** to match the source text: SN-8 (`ruff`/`flake8`, not
  `black`), TE-11 (`--ff` preferred over `--lf`), RE-5 (no "scholarly artifact"),
  GE-4 (no "four error sources" count), DM-12 (no GDPR clause), DM-8 (no
  cloud-object-storage clause), and others.
- **Coverage gaps closed** with the 10 previously-uncited posts —
  `global-variables` (SN-15), `code-formatting-tools` + `essential-tools-for-writing-better`
  (SN-16), `coding-portably` (RE-7), the three `data-formats-*` posts (DM-21).
- **44 new principles** added across all sections, each with its source slug and a
  verbatim supporting quote.

## Verification result

- Rubric grew 112 → **156 criteria**; **no duplicate IDs**; **all 112 original IDs
  preserved**.
- Every cited slug (47 unique after the additions) confirmed present in the
  enumerated real-corpus set.

## Reproducibility

The audit was run as a deterministic workflow; its script is preserved in the
session's `workflows/scripts/` directory. The blog was enumerated 2026-06-04;
post content may evolve, so future re-verification should re-enumerate the
sitemap first.
