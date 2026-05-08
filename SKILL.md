---
name: paper-fraud-auditor
description: Use when auditing a scientific paper PDF for possible image reuse, suspicious experimental data patterns, digit/Benford anomalies, table inconsistencies, fabricated-looking trends, or paper fraud risk. Converts PDFs with MinerU, builds an evidence ledger, performs strict multi-pass review, and can generate annotated evidence images for high-risk tables.
---

# Paper Fraud Auditor

Use this skill when the user wants to审查论文 PDF、识别论文造假、检查论文图片/表格/实验数据异常、使用耿同学方法论、本福特定律、MinerU PDF 转 Markdown，或要求对论文做严格多轮审查。

## Non-negotiables

- Do not claim a paper is fraudulent from one signal. Say "异常", "疑点", "需要人工复核", or "高风险证据链".
- Every finding must cite evidence location: page, figure/table number, markdown line or content block, image path, table row/column, and original value.
- Benford's Law is gated by applicability. If sample size, range, or data type is unsuitable, say it is not applicable and use terminal-digit/roundness checks instead.
- Treat API tokens as secrets. Never write MinerU tokens into `SKILL.md`, scripts, reports, command history, or examples. Read `MINERU_API_TOKEN` from the environment.
- Prefer deterministic scripts for extraction/statistical checks, then use agents for interpretation, visual review, and adversarial explanation testing.
- Evidence images must be traceable. Prefer deterministic annotated table renders from the original XLSX/PDF extraction over decorative AI images. Use generative image tools only for presentation/overview graphics, not as primary evidence.

## Required References

Read only what is needed:

- `references/geng-methodology.md`: image identity conflicts, data duplication, last-digit patterns, formula reverse-checks, trend/template checks, domain sanity, author-response pressure tests.
- `references/benfords-law.md`: Benford formula, applicability boundaries, misuse warnings, and reporting language.
- `references/mineru-api.md`: MinerU API flow and output file expectations.
- `references/report-rubric.md`: evidence levels and final report template.
- `references/image-backend-config.md`: optional AI image model endpoint/API configuration for presentation graphics, not primary evidence.

## Pipeline

1. **Convert PDF with MinerU**
   - Ask the user for a PDF path or URL if none is provided.
   - Set `MINERU_API_TOKEN` in the environment outside the skill files.
   - Run:

```bash
python3 scripts/mineru_convert.py /path/to/paper.pdf --output /path/to/audit-workdir
```

   - Expected output: extracted zip contents, `full.md`, `*_content_list.json`, `*_middle.json`, image files, and `mineru_manifest.json`.

2. **Build the evidence ledger**
   - Use MinerU outputs as source of truth.
   - Run:

```bash
python3 scripts/build_evidence_ledger.py /path/to/audit-workdir \
  --output /path/to/audit-workdir/evidence_ledger.json
```

   - Expected output: `evidence_ledger.json` indexing text, tables, figures/charts/images, captions, page numbers, bounding boxes, image paths, markdown lines, content blocks, table row/column/cell values, and original values.
   - Preserve original values. Do not normalize away suspicious formatting.

3. **Run deterministic numeric checks**

```bash
python3 scripts/numeric_forensics.py /path/to/audit-workdir --output /path/to/audit-workdir/numeric_forensics.json
```

   - Default `--scope auto` prefers table numbers when enough are available, avoiding reference years/page numbers polluting the statistics.
   - Use this for exact duplicates, repeated decimals, terminal digits, roundness, Benford applicability, Benford deviation, and simple column relationship hints.
   - Treat the JSON as leads, not verdicts.

4. **Perform multi-agent audit when subagents are available**
   - Image Forensics Agent: same base image/different label, same subject/different signal, duplicated panels, local copy-paste.
   - Data Duplication Agent: repeated rows/columns, fixed offsets, repeated fractional parts, lightly modified copies.
   - Digit Pattern Agent: terminal 0/5 concentration, over-neat decimals, suspicious roundness.
   - Math Consistency Agent: percentages vs counts, reverse-engineered denominators, impossible rounding, fixed formulas.
   - Benford Agent: applicability first, then first-digit analysis only when allowed.
   - Distribution Agent: plot tables when useful, compare curve shapes and noise texture.
   - Domain Sanity Agent: measurement precision, biological/experimental plausibility, instrument/domain expectations.
   - Defense Agent: construct the strongest benign explanation for each anomaly and test whether it explains all related evidence.
   - Judge Agent: merge evidence, remove weak duplicates, assign risk level, and write the final report.

5. **Use vision carefully**
   - For each suspect image/panel, ask vision to describe concrete visual identity: subject outline, body/posture, cell/gel structure, signal layer, labels, and caption.
   - Do not ask vision to "decide fraud". Ask whether visual identity and experimental labels conflict.
   - Compare images pairwise when possible using both visual review and any available similarity/crop evidence.

6. **Generate annotated evidence images when useful**
   - For high-risk table or Source Data findings, render the original cells into PNG evidence cards with highlighted anomalous ranges and concise annotations.
   - Use this when the user asks for 生图、证据图、截图、高风险表格标注, or when the final report would benefit from visual evidence.
   - Default to deterministic evidence rendering; it needs no AI image API and is suitable for audit exhibits.
   - For Source Data audit JSON containing `fixed_difference_findings` or `terminal_findings`, run:

```bash
python3 scripts/render_evidence_tables.py \
  --audit-json /path/to/blind_source_audit.json \
  --xlsx-root /path/to/source-data-xlsx-folder \
  --output /path/to/audit-workdir/evidence_images
```

   - Expected output: annotated PNG files plus `evidence_images_manifest.json`.
   - Each evidence image must preserve source file, sheet, range, examples, and risk note. Do not replace the written evidence ledger with images; images are a presentation layer.
   - If the user wants AI-generated cover images, infographics, or visual abstracts, read `references/image-backend-config.md`. Ask for or use `PAPER_AUDITOR_IMAGE_API_KEY`, `PAPER_AUDITOR_IMAGE_API_URL`, and `PAPER_AUDITOR_IMAGE_MODEL` only for that optional presentation layer. Never store keys in skill files or reports.

7. **Final report**
   - Start with the risk level and strongest evidence chain.
   - Then list findings from strongest to weakest.
   - For each finding include: evidence, method used, why it is suspicious, benign explanations, pressure-test result, confidence, and recommended manual verification.
   - Embed or link evidence images for the highest-risk findings when generated.
   - End with limitations: MinerU extraction quality, PDF image resolution, sample-size constraints, and whether raw data/original images are needed.

## Risk Language

- **Low**: no strong anomaly; only weak or explainable signals.
- **Medium**: multiple weak-to-moderate anomalies requiring human review.
- **High**: independent evidence lines agree, such as repeated data plus impossible formula relation.
- **Critical**: image identity conflict plus numeric generation artifacts or reverse-engineered data relationships.

## Audit Discipline

- A neat number is not proof.
- Benford failure is not proof.
- A duplicated image can be benign only if the label, signal, caption, and author explanation remain consistent.
- The strongest evidence is a network: image identity conflict, mechanical numeric pattern, reversed formula generation, and failed benign explanation.
