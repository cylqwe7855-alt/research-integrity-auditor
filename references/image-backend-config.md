# Optional AI Image Backend Configuration

Use this reference only when the user wants AI-generated presentation graphics, cover images, infographic summaries, or visual abstracts in addition to deterministic evidence images.

## Two Image Modes

1. **Deterministic evidence render**
   - No API key required.
   - Rendered from original XLSX/PDF-extracted cells.
   - Use for audit evidence, high-risk table annotations, source-data screenshots, and report exhibits.
   - Primary script: `scripts/render_evidence_tables.py`.

2. **AI-generated presentation image**
   - Optional API key and endpoint required.
   - Use only for overview visuals, report covers, infographic summaries, and explanatory diagrams.
   - Never use AI-generated table values as evidence. If a table appears in an AI-generated visual, it must be based on the deterministic evidence render or summarized with explicit source citations.

## Environment Variables

Never store API keys in `SKILL.md`, reports, prompt examples, or committed config files. Read them from environment variables:

```bash
export PAPER_AUDITOR_IMAGE_API_KEY="..."
export PAPER_AUDITOR_IMAGE_API_URL="https://example.com/v1/images/generations"
export PAPER_AUDITOR_IMAGE_MODEL="your-image-model"
```

Optional:

```bash
export PAPER_AUDITOR_IMAGE_SIZE="1536x1024"
export PAPER_AUDITOR_IMAGE_PROVIDER="openai-compatible"
```

## Generic Request Shape

For OpenAI-compatible image APIs, prefer this JSON body:

```json
{
  "model": "$PAPER_AUDITOR_IMAGE_MODEL",
  "prompt": "Evidence-grounded visual prompt...",
  "size": "$PAPER_AUDITOR_IMAGE_SIZE"
}
```

If the provider uses a different schema, adapt the request locally, but keep these safeguards:

- The prompt must say the visual is an explanatory/summary graphic, not raw evidence.
- Do not invent numeric values, figure labels, author names, or journal actions.
- Use generated visuals only after deterministic findings have been written to an evidence ledger.
- Link the generated image to the exact audit report and evidence PNGs it summarizes.

## Recommended Prompt Pattern

```text
Create a clean research-integrity audit infographic summarizing verified source-data anomalies.
Use only these findings:
- [file/sheet/range]: [finding summary]
- [file/sheet/range]: [finding summary]

Style: precise, editorial, restrained, white background, red risk annotations, spreadsheet/table motifs.
Do not add unsupported claims. Do not imply final fraud verdict. Label the graphic as "High-risk anomaly evidence, requires manual verification".
```

## When To Ask The User

Ask for API details only when:

- the user explicitly asks for AI-generated images rather than deterministic evidence renders;
- no built-in image generation tool is available;
- or the user wants to use a specific model/provider.

Do not ask for API details when deterministic evidence PNGs are sufficient.
