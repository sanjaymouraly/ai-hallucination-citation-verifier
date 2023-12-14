# Deterministic fixture evaluation

Run date: 2026-10-16 · Examples: 33

This small, hand-authored fixture set is a regression aid, not an external benchmark or a claim of real-world accuracy. The labels are scenario expectations and the rule-based output is intentionally conservative. It measures only these local examples.

- Accuracy: **1.000**
- Macro F1: **1.000**

## Per-status metrics

| Status | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| `citation_missing` | 1.000 | 1.000 | 1.000 | 2 |
| `contradicted` | 1.000 | 1.000 | 1.000 | 5 |
| `insufficient_evidence` | 1.000 | 1.000 | 1.000 | 3 |
| `needs_human_review` | 1.000 | 1.000 | 1.000 | 6 |
| `not_applicable` | 1.000 | 1.000 | 1.000 | 3 |
| `partially_supported` | 1.000 | 1.000 | 1.000 | 5 |
| `source_unavailable` | 1.000 | 1.000 | 1.000 | 2 |
| `supported` | 1.000 | 1.000 | 1.000 | 7 |

## Cases requiring attention

All fixture expectations matched in this run.

## Interpretation

These results do not estimate the probability that any claim is true. Retrieval and labels remain sensitive to source quality, paraphrase, context, chronology, qualifiers, and domain-specific language. Run `python scripts/evaluate.py` after changes to reproduce this local check.
