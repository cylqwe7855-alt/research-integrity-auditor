# Benford's Law Reference

Use this only after checking applicability.

## Formula

For first digit `d in 1..9`:

`P(d) = log10(1 + 1 / d)`

Expected distribution:

| First digit | Probability |
|---|---:|
| 1 | 30.1% |
| 2 | 17.6% |
| 3 | 12.5% |
| 4 | 9.7% |
| 5 | 7.9% |
| 6 | 6.7% |
| 7 | 5.8% |
| 8 | 5.1% |
| 9 | 4.6% |

## Applicability Gate

Benford is more appropriate when the dataset:

- Contains naturally generated quantity values.
- Has enough observations, preferably hundreds or more.
- Spans multiple orders of magnitude.
- Is not strongly bounded by human rules, measurement limits, or experimental design.
- Is not an identifier or label.

## Usually Not Applicable

Do not use Benford as evidence for:

- Narrow biological measurements, such as mouse weight around 18-25g.
- Proportions, percentages, p-values, fold changes, normalized values, or values mostly in 0-1.
- IDs, sample labels, page numbers, DOI fragments, accession numbers, reference numbers.
- Small samples of only dozens of values.
- Data with artificial thresholds, caps, or fixed formatting rules.

## Correct Reporting

Good language:

- "Benford is not applicable because the data are narrow-range percentages."
- "Benford is partially applicable; treat deviation as a weak lead only."
- "The first-digit distribution deviates from Benford in a dataset that appears applicable; this warrants further review."

Bad language:

- "Benford proves fraud."
- "The data fail Benford, therefore the paper is fake."

## Relationship to the Geng-style Method

For many paper datasets, terminal-digit and roundness checks are more useful than Benford. Benford should be a smoke alarm, not a judge. Stronger evidence comes from overlap with repeated values, impossible formulas, reverse-engineered percentages, or image identity conflicts.
