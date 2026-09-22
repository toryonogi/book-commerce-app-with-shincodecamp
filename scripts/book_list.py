#!/usr/bin/env python3
"""書籍一覧へ ProductID を追加する。

既存の ProductID は行を増やさず、タイトル・status・取得日を表示する。
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

PRODUCT_ID_PATTERN = re.compile(r"KP(\d+)", re.IGNORECASE)
PRODUCT_ID_EXACT = re.compile(r"KP(\d+)", re.IGNORECASE)
DEFAULT_LIST = Path(__file__).resolve().parent.parent / "data" / "books_master.csv"
STATUS_NEW = "未取得"


@dataclass(frozen=True)
class AddResult:
    product_id: str
    action: str
    title: str = ""
    status: str = ""
    captured_at: str = ""


@dataclass(frozen=True)
class RejectedToken:
    token: str


def format_product_id(digits: str) -> str:
    number = int(digits)
    if number < 100_000_000:
        return f"KP{number:08d}"
    return f"KP{number}"


def product_id_key(value: str) -> int | None:
    text = unicodedata.normalize("NFKC", value).strip()
    match = PRODUCT_ID_EXACT.fullmatch(text)
    if match is None:
        return None
    return int(match.group(1))


def extract_product_ids(token: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", token)
    found: list[str] = []
    seen: set[str] = set()
    for digits in PRODUCT_ID_PATTERN.findall(normalized):
        product_id = format_product_id(digits)
        if product_id not in seen:
            seen.add(product_id)
            found.append(product_id)
    return found


def load_books(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"ヘッダがありません: {path}")
        fieldnames = list(reader.fieldnames)
        rows = [{key: value or "" for key, value in row.items()} for row in reader]
    missing = [name for name in ("ProductID", "status") if name not in fieldnames]
    if missing:
        raise ValueError(f"必要な列がありません: {', '.join(missing)}")
    return fieldnames, rows


def index_by_product_id(rows: list[dict[str, str]]) -> dict[int, dict[str, str]]:
    index: dict[int, dict[str, str]] = {}
    for row in rows:
        key = product_id_key(row.get("ProductID", ""))
        if key is not None and key not in index:
            index[key] = row
    return index


def append_row(path: Path, fieldnames: list[str], row: dict[str, str]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writerow(row)
    payload = buffer.getvalue().encode("utf-8")
    with path.open("a+b") as handle:
        handle.seek(0, io.SEEK_END)
        if handle.tell() > 0:
            handle.seek(-1, io.SEEK_END)
            needs_newline = handle.read(1) != b"\n"
            if needs_newline:
                handle.write(b"\n")
        handle.write(payload)


def add_product_ids(path: Path, tokens: list[str]) -> tuple[list[AddResult], list[RejectedToken]]:
    fieldnames, rows = load_books(path)
    index = index_by_product_id(rows)
    results: list[AddResult] = []
    rejected: list[RejectedToken] = []

    for token in tokens:
        product_ids = extract_product_ids(token)
        if not product_ids:
            rejected.append(RejectedToken(token))
            continue
        for product_id in product_ids:
            key = product_id_key(product_id)
            if key is None:
                rejected.append(RejectedToken(token))
                continue
            existing = index.get(key)
            if existing is not None:
                results.append(
                    AddResult(
                        product_id=existing.get("ProductID") or product_id,
                        action="existing",
                        title=existing.get("タイトル", ""),
                        status=existing.get("status", ""),
                        captured_at=existing.get("captured_at", ""),
                    )
                )
                continue
            row = {name: "" for name in fieldnames}
            row["ProductID"] = product_id
            row["status"] = STATUS_NEW
            append_row(path, fieldnames, row)
            index[key] = row
            results.append(AddResult(product_id=product_id, action="added", status=STATUS_NEW))
    return results, rejected


def format_result(result: AddResult) -> str:
    if result.action == "added":
        return f"追加  {result.product_id}  status: {result.status}"
    return (
        f"既存  {result.product_id}  タイトル: {result.title}  "
        f"status: {result.status}  取得日: {result.captured_at}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="書籍一覧へ ProductID を追加する。既存IDは行を増やさない。")
    parser.add_argument(
        "--list",
        type=Path,
        default=DEFAULT_LIST,
        help=f"一覧CSV（既定: {DEFAULT_LIST})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_parser = subparsers.add_parser("add", help="ProductID を追加する")
    add_parser.add_argument("ids", nargs="+", help="ProductID、またはそれを含むURL")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.list.is_file():
        print(f"一覧が見つかりません: {args.list}", file=sys.stderr)
        return 1
    try:
        results, rejected = add_product_ids(args.list, args.ids)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    for result in results:
        print(format_result(result))
    for item in rejected:
        print(f"IDを読み取れません: {item.token}", file=sys.stderr)
    if rejected or not results:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
