# MinerU API Notes

Source: MinerU API docs at `https://mineru.net/apiManage/docs` and MinerU output format docs.

## Token Handling

- Read token from `MINERU_API_TOKEN`.
- Send header: `Authorization: Bearer <token>`.
- Never store the token in skill files, reports, manifests, or logs.

## Precise Parsing API

Use the precise parsing API for paper audits because it supports higher-quality structure, tables, formulas, images, and JSON outputs.

Limits from docs:

- File size up to 200MB.
- Page count up to 200 pages.
- Supports PDF, images, doc/docx, ppt/pptx.
- `model_version`: `pipeline`, `vlm`, or `MinerU-HTML`; default to `vlm` for PDFs unless there is a reason to choose otherwise.

## Local File Flow

1. POST `https://mineru.net/api/v4/file-urls/batch`
2. Body includes `files: [{"name": "...", "data_id": "..."}]`, `model_version`, `enable_table`, `enable_formula`, `language`.
3. Response includes `batch_id` and one or more upload URLs.
4. PUT local file bytes to the upload URL. Do not set `Content-Type`.
5. Poll GET `https://mineru.net/api/v4/extract-results/batch/{batch_id}`.
6. When state is `done`, download `full_zip_url`.

## URL Flow

1. POST `https://mineru.net/api/v4/extract/task`
2. Body includes `url`, `model_version`, `enable_table`, `enable_formula`, `language`.
3. Poll GET `https://mineru.net/api/v4/extract/task/{task_id}`.
4. When state is `done`, download `full_zip_url`.

## Expected Output Files

MinerU zip commonly includes:

- `full.md`: markdown output.
- `*_content_list.json`: flat readable content blocks in reading order.
- `*_middle.json`: detailed page/block structures, including page indices, bounding boxes, images, tables, captions, and page sizes.
- `*_model.json`: model inference results.
- `images/`: extracted image, chart, table, and equation crops.
- Optional visual debugging PDFs such as layout/span files depending on backend.

Use `content_list.json` as the easiest source for evidence indexing; use `middle.json` when bounding boxes and page structure matter.
