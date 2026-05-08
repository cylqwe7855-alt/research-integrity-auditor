![论文造假审查Skill](assets/paper-fraud-auditor-banner.png)

# Research Integrity Auditor

A Claude/Codex skill for structured research-integrity review of scientific papers. It helps convert papers with MinerU, build a citeable evidence ledger, run deterministic numeric-forensics checks, and render annotated evidence images for suspicious source-data tables.

## 中文介绍

这是一个用于论文科研诚信审查的 Claude/Codex Skill。它可以辅助审查论文 PDF、图表、实验数据和源数据表格中的异常线索：通过 MinerU 转换论文，自动构建可引用的证据台账，运行数字取证检查，并为高风险表格生成确定性的证据标注图。

它的目标不是直接“判定造假”，而是帮助你整理可复核的异常证据链：每条发现都应包含页码、图表编号、原始值、图片路径、Markdown 行号或内容块位置，并明确说明可能的善意解释和人工复核建议。

## What it does

- Converts PDFs or public paper URLs with MinerU.
- Builds `evidence_ledger.json` from MinerU outputs, including text, tables, figures/images, captions, pages, bounding boxes, markdown lines, content blocks, table cells, and original values.
- Runs deterministic numeric checks for repeated values, repeated fractional parts, terminal-digit patterns, Benford applicability, and simple fixed-difference/fixed-ratio table relationships.
- Renders deterministic evidence PNGs from source XLSX audit findings.
- Guides multi-pass review with careful risk language and manual verification requirements.

## What it does not do

- It does not prove fraud.
- It does not replace journal, institutional, or expert investigation.
- It does not use AI-generated images as evidence.
- It does not store API tokens or secrets.

Use outputs as audit leads that require human review.

## One-command install

Install the skill into `~/.claude/skills/paper-fraud-auditor`:

```bash
npm exec --package github:cylqwe7855-alt/research-integrity-auditor -- research-integrity-auditor
```

Short form:

```bash
npx github:cylqwe7855-alt/research-integrity-auditor
```

Install into the current project instead:

```bash
npm exec --package github:cylqwe7855-alt/research-integrity-auditor -- research-integrity-auditor --project
```

Restart Claude Code if the skill does not appear immediately.

## Quick start

Set your MinerU token outside the repository:

```bash
export MINERU_API_TOKEN="..."
```

Convert a paper:

```bash
python3 scripts/mineru_convert.py /path/to/paper.pdf --output /path/to/audit-workdir
```

Build the evidence ledger:

```bash
python3 scripts/build_evidence_ledger.py /path/to/audit-workdir \
  --output /path/to/audit-workdir/evidence_ledger.json
```

Run numeric forensics:

```bash
python3 scripts/numeric_forensics.py /path/to/audit-workdir \
  --output /path/to/audit-workdir/numeric_forensics.json
```

Render evidence images from source-data audit JSON:

```bash
python3 scripts/render_evidence_tables.py \
  --audit-json /path/to/blind_source_audit.json \
  --xlsx-root /path/to/source-data-xlsx-folder \
  --output /path/to/audit-workdir/evidence_images
```

## Safety and responsible use

Do not claim that a paper is fraudulent from a single signal. Report concrete anomalies, cite exact evidence locations, pressure-test benign explanations, and state limitations clearly.

## License

MIT
