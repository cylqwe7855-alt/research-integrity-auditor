#!/usr/bin/env python3
"""Generate numeric-forensics leads from MinerU markdown/content output.

This script finds leads, not verdicts. Human/agent review must interpret them.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import re
import statistics
from decimal import Decimal, InvalidOperation


NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?%?"
)


def normalize_number(raw: str) -> Decimal | None:
    value = raw.replace(",", "")
    if value.endswith("%"):
        value = value[:-1]
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def first_digit(value: Decimal) -> str | None:
    if value == 0:
        return None
    s = str(value).lstrip("-+")
    if "e" in s.lower():
        try:
            s = format(value, "f")
        except Exception:
            return None
    s = s.replace(".", "").lstrip("0")
    return s[0] if s else None


def decimal_from_record(record: dict) -> Decimal | None:
    try:
        value = Decimal(record["value"])
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite():
        return None
    return value


def plausible_quantity(value: Decimal) -> bool:
    # Scientific papers contain many huge identifiers, DOI fragments, image hashes,
    # references, and accession numbers. Keep ordinary measured quantities for
    # digit/Benford leads; evidence review can still inspect raw text separately.
    magnitude = value.copy_abs()
    return Decimal("0") < magnitude < Decimal("1e12")


def terminal_digit(raw: str) -> str | None:
    s = raw.strip().rstrip("%").replace(",", "")
    digits = [c for c in s if c.isdigit()]
    return digits[-1] if digits else None


def fractional_part(raw: str) -> str | None:
    s = raw.strip().rstrip("%").replace(",", "")
    if "." not in s:
        return None
    return s.split(".", 1)[1].lower().split("e", 1)[0]


def find_full_md(root: pathlib.Path) -> pathlib.Path | None:
    candidates = sorted(root.rglob("full.md"))
    if candidates:
        return candidates[0]
    markdown = sorted(root.rglob("*.md"))
    return markdown[0] if markdown else None


def extract_numbers_from_markdown(md_path: pathlib.Path) -> list[dict]:
    records = []
    lines = md_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line_no, line in enumerate(lines, start=1):
        for match in NUMBER_RE.finditer(line):
            raw = match.group(0)
            value = normalize_number(raw)
            if value is None:
                continue
            records.append(
                {
                    "raw": raw,
                    "value": str(value),
                    "line": line_no,
                    "context": line.strip()[:500],
                }
            )
    return records


def extract_markdown_tables(md_path: pathlib.Path) -> list[dict]:
    tables = []
    current = []
    start_line = None
    lines = md_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for idx, line in enumerate(lines, start=1):
        if "|" in line and re.search(r"\d", line):
            if not current:
                start_line = idx
            current.append(line)
        else:
            if len(current) >= 2:
                tables.append({"start_line": start_line, "rows": current})
            current = []
            start_line = None
    if len(current) >= 2:
        tables.append({"start_line": start_line, "rows": current})
    return tables


def table_line_numbers(tables: list[dict]) -> set[int]:
    lines = set()
    for table in tables:
        start = table["start_line"]
        for offset in range(len(table["rows"])):
            lines.add(start + offset)
    return lines


def select_scope(records: list[dict], tables: list[dict], scope: str) -> tuple[list[dict], str]:
    if scope == "all":
        return records, "all"
    table_lines = table_line_numbers(tables)
    table_records = [record for record in records if record["line"] in table_lines]
    if scope == "tables":
        return table_records, "tables"
    if len(table_records) >= 20:
        return table_records, "tables"
    return records, "all_fallback_table_numbers_lt_20"


def parse_table_numbers(table: dict) -> list[list[Decimal | None]]:
    parsed = []
    for row in table["rows"]:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        num_row = []
        for cell in cells:
            matches = NUMBER_RE.findall(cell)
            if len(matches) == 1:
                num_row.append(normalize_number(matches[0]))
            else:
                num_row.append(None)
        parsed.append(num_row)
    return parsed


def duplicate_analysis(records: list[dict]) -> dict:
    counter = collections.Counter(record["value"] for record in records)
    duplicates = [
        {"value": value, "count": count}
        for value, count in counter.most_common()
        if count >= 3
    ][:50]
    fractional_counter = collections.Counter(
        fractional_part(record["raw"]) for record in records if fractional_part(record["raw"])
    )
    repeated_fractional = [
        {"fractional_part": value, "count": count}
        for value, count in fractional_counter.most_common()
        if count >= 3
    ][:50]
    return {"repeated_values": duplicates, "repeated_fractional_parts": repeated_fractional}


def digit_analysis(records: list[dict]) -> dict:
    terminals = [terminal_digit(record["raw"]) for record in records]
    terminals = [digit for digit in terminals if digit is not None]
    terminal_counts = collections.Counter(terminals)
    n = len(terminals)
    zero_five = terminal_counts.get("0", 0) + terminal_counts.get("5", 0)
    first_digits = []
    for record in records:
        value = decimal_from_record(record)
        if value is not None and plausible_quantity(value):
            first_digits.append(first_digit(value))
    first_digits = [digit for digit in first_digits if digit is not None]
    return {
        "terminal_digit_counts": dict(sorted(terminal_counts.items())),
        "terminal_0_or_5_rate": zero_five / n if n else None,
        "first_digit_counts": dict(sorted(collections.Counter(first_digits).items())),
    }


def benford_analysis(records: list[dict]) -> dict:
    values = []
    for record in records:
        value = decimal_from_record(record)
        if value is not None and plausible_quantity(value):
            values.append(value.copy_abs())
    if not values:
        return {"applicability": "not_applicable", "reason": "no positive values"}
    min_value = min(values)
    max_value = max(values)
    n = len(values)
    ratio = float(max_value / min_value) if min_value != 0 else float("inf")
    orders = math.log10(ratio) if ratio > 0 else 0
    applicability = "applicable" if n >= 100 and orders >= 2 else "not_applicable"
    reason = f"n={n}, max/min={ratio:.3g}, orders={orders:.2f}"

    counts = collections.Counter(first_digit(value) for value in values)
    counts.pop(None, None)
    expected = {str(d): math.log10(1 + 1 / d) for d in range(1, 10)}
    observed = {str(d): counts.get(str(d), 0) / n for d in range(1, 10)}
    mad = sum(abs(observed[d] - expected[d]) for d in expected) / 9
    return {
        "applicability": applicability,
        "reason": reason,
        "sample_size": n,
        "orders_of_magnitude": orders,
        "observed": observed,
        "expected": expected,
        "mean_absolute_deviation": mad,
    }


def table_relationships(tables: list[dict]) -> list[dict]:
    findings = []
    for table_index, table in enumerate(tables, start=1):
        matrix = parse_table_numbers(table)
        if not matrix:
            continue
        width = max(len(row) for row in matrix)
        columns = []
        for col in range(width):
            values = []
            for row in matrix:
                if col < len(row) and row[col] is not None:
                    values.append(row[col])
            columns.append(values)
        for i in range(width):
            for j in range(i + 1, width):
                a = columns[i]
                b = columns[j]
                if len(a) < 8 or len(a) != len(b):
                    continue
                diffs = [x - y for x, y in zip(a, b)]
                rounded_diffs = [str(diff.quantize(Decimal("0.0001"))) for diff in diffs]
                diff_counts = collections.Counter(rounded_diffs)
                top_diff, top_count = diff_counts.most_common(1)[0]
                if top_count / len(diffs) >= 0.8:
                    findings.append(
                        {
                            "table_index": table_index,
                            "start_line": table["start_line"],
                            "column_pair": [i + 1, j + 1],
                            "relationship": "fixed_difference_candidate",
                            "difference": top_diff,
                            "support": f"{top_count}/{len(diffs)}",
                        }
                    )
                ratios = []
                for x, y in zip(a, b):
                    if y != 0:
                        ratios.append(x / y)
                if len(ratios) >= 8:
                    rounded_ratios = [str(ratio.quantize(Decimal("0.0001"))) for ratio in ratios]
                    ratio_counts = collections.Counter(rounded_ratios)
                    top_ratio, top_ratio_count = ratio_counts.most_common(1)[0]
                    if top_ratio_count / len(ratios) >= 0.8:
                        findings.append(
                            {
                                "table_index": table_index,
                                "start_line": table["start_line"],
                                "column_pair": [i + 1, j + 1],
                                "relationship": "fixed_ratio_candidate",
                                "ratio": top_ratio,
                                "support": f"{top_ratio_count}/{len(ratios)}",
                            }
                        )
    return findings[:100]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract numeric forensic leads from MinerU output.")
    parser.add_argument("input", help="MinerU output directory or markdown file.")
    parser.add_argument("--output", required=True, help="JSON output path.")
    parser.add_argument(
        "--scope",
        choices=["auto", "tables", "all"],
        default="auto",
        help="auto prefers table numbers when at least 20 are available.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = pathlib.Path(args.input).expanduser().resolve()
    if input_path.is_dir():
        md_path = find_full_md(input_path)
    else:
        md_path = input_path
    if md_path is None or not md_path.exists():
        raise FileNotFoundError("Could not find markdown file")

    all_records = extract_numbers_from_markdown(md_path)
    tables = extract_markdown_tables(md_path)
    records, effective_scope = select_scope(all_records, tables, args.scope)
    result = {
        "source_markdown": str(md_path),
        "scope": args.scope,
        "effective_scope": effective_scope,
        "all_number_count": len(all_records),
        "number_count": len(records),
        "table_count": len(tables),
        "duplicates": duplicate_analysis(records),
        "digits": digit_analysis(records),
        "benford": benford_analysis(records),
        "table_relationships": table_relationships(tables),
        "records_sample": records[:50],
    }
    output = pathlib.Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "numbers": len(records), "tables": len(tables)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
