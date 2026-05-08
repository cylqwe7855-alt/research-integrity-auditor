# Report Rubric

## Risk Levels

- **Low**: no strong anomaly; only weak or explainable signals.
- **Medium**: several weak/moderate anomalies that require manual review.
- **High**: independent evidence lines agree, such as repeated values plus fixed formula relationships.
- **Critical**: direct image identity conflict or same-subject/different-signal evidence, especially when supported by numeric generation artifacts.

## Finding Template

For each finding:

```text
Finding ID:
Risk:
Evidence type:
Location:
Observed pattern:
Methodology used:
Why suspicious:
Possible benign explanation:
Pressure-test result:
Confidence:
Recommended manual verification:
```

## Strong Evidence Chains

Prioritize chains that combine independent signals:

- Image identity conflict + inconsistent figure labels/captions.
- Repeated table data + fixed offset or fixed multiplier relationship.
- Terminal-digit concentration + repeated fractional parts + impossible rounding.
- Percentage/count reverse engineering + same denominator appearing unnaturally often.
- Benford deviation in an applicable dataset + other mechanical numeric evidence.

## Limitations Section

Always include:

- MinerU extraction may misread tables, formulas, or captions.
- Low-resolution PDF images can hide or create visual artifacts.
- Benford may be invalid for narrow-range or small-sample scientific data.
- Without original raw data and uncropped images, conclusions remain audit leads, not final proof.
