#!/usr/bin/env python3
"""KinoDen の書誌詳細から、空のタイトル・著者・出版社・ISBN だけを埋める。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PRODUCT_ID_COLUMN = 1
TITLE_COLUMN = 4
AUTHOR_COLUMN = 5
PUBLISHER_COLUMN = 6
ISBN_COLUMN = 7
COLUMNS = {
    "title": TITLE_COLUMN,
    "author": AUTHOR_COLUMN,
    "publisher": PUBLISHER_COLUMN,
    "isbn": ISBN_COLUMN,
}
API_URL = (
    "https://api-v4.breader.cloud/api/v1/getbookinfoforcomp"
    "?code=kgcactU2AvtwaN2gEgnzEYfo0lkbmwNvHnzlqa2nsH60SAlRFs6KxA=="
)
DEFAULT_COMPCODE = "library.pref.hokkaido"


def blank(value: str) -> bool:
    return value.strip() == ""


def apply_bibliography(row: list[str], info: dict[str, str]) -> list[str]:
    """空のセルだけ埋める。入力済みのセルは変えない。"""
    width = max(len(row), ISBN_COLUMN + 1)
    updated = list(row) + [""] * (width - len(row))
    for key, index in COLUMNS.items():
        value = (info.get(key) or "").strip()
        if value and blank(updated[index]):
            updated[index] = value
    return updated


def bibliography_from_bookinfo(bookinfo: dict) -> dict[str, str]:
    authors = bookinfo.get("author") or []
    if isinstance(authors, str):
        author = authors.strip()
    else:
        author = " ".join(str(name).strip() for name in authors if str(name).strip())
    return {
        "title": str(bookinfo.get("title") or "").strip(),
        "author": author,
        "publisher": str(bookinfo.get("publisher") or "").strip(),
        "isbn": str(bookinfo.get("isbn") or "").strip(),
    }


def fetch_bibliography(product_id: str, compcode: str = DEFAULT_COMPCODE, timeout: float = 30) -> dict[str, str]:
    payload = json.dumps({"compcode": compcode, "productID": product_id}).encode()
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Origin": "https://kinoden.kinokuniya.co.jp",
            "Referer": f"https://kinoden.kinokuniya.co.jp/{compcode}/bookdetail/p/{product_id}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    bookinfo = data.get("bookinfo") or {}
    if not bookinfo.get("title") and not bookinfo.get("isbn"):
        raise LookupError(f"書誌がありません: {product_id}")
    return bibliography_from_bookinfo(bookinfo)


def fetch_many(product_ids: list[str], workers: int = 6) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    errors: dict[str, str] = {}

    def load(product_id: str) -> tuple[str, dict[str, str] | None, str]:
        delay = 1.0
        last_error = "取得できませんでした"
        for _ in range(4):
            try:
                return product_id, fetch_bibliography(product_id), ""
            except urllib.error.HTTPError as error:
                last_error = f"HTTP {error.code}"
                if error.code not in {429, 500, 502, 503, 504}:
                    break
            except Exception as error:  # noqa: BLE001 - 再試行のために理由だけ残す
                last_error = str(error)
            time.sleep(delay)
            delay *= 2
        return product_id, None, last_error

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(load, product_id) for product_id in product_ids]
        for future in as_completed(futures):
            product_id, info, error = future.result()
            if info is None:
                errors[product_id] = error
            else:
                found[product_id] = info
    return found, errors


def fill_rows(rows: list[list[str]], bibliographies: dict[str, dict[str, str]]) -> tuple[list[list[str]], dict[str, int]]:
    counts = {"title": 0, "author": 0, "publisher": 0, "isbn": 0, "rows": 0}
    filled_rows: list[list[str]] = []
    for row in rows:
        product_id = row[PRODUCT_ID_COLUMN].strip() if len(row) > PRODUCT_ID_COLUMN else ""
        info = bibliographies.get(product_id)
        if not info:
            filled_rows.append(row)
            continue
        before = list(row)
        updated = apply_bibliography(row, info)
        changed = False
        for key, index in COLUMNS.items():
            old = before[index].strip() if len(before) > index else ""
            new = updated[index].strip() if len(updated) > index else ""
            if not old and new:
                counts[key] += 1
                changed = True
        if changed:
            counts["rows"] += 1
        filled_rows.append(updated)
    return filled_rows, counts


def product_ids_with_gaps(rows: list[list[str]]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if len(row) <= PRODUCT_ID_COLUMN:
            continue
        product_id = row[PRODUCT_ID_COLUMN].strip()
        if not product_id.startswith("KP") or product_id in seen:
            continue
        needs_fill = any(len(row) <= index or blank(row[index]) for index in COLUMNS.values())
        if needs_fill:
            seen.add(product_id)
            ids.append(product_id)
    return ids


def read_csv(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def write_csv(path: Path, rows: list[list[str]]) -> None:
    width = max(len(row) for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        for row in rows:
            writer.writerow(row + [""] * (width - len(row)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="空の書誌欄を KinoDen の書誌詳細から埋める。")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)

    rows = read_csv(args.source)
    product_ids = product_ids_with_gaps(rows[2:])
    found, errors = fetch_many(product_ids)
    filled_rows, counts = fill_rows(rows, found)
    write_csv(args.destination, filled_rows)
    print(
        f"対象 {len(product_ids)} 件 / 更新 {counts['rows']} 行 / "
        f"タイトル {counts['title']} / 著者 {counts['author']} / "
        f"出版社 {counts['publisher']} / ISBN {counts['isbn']} / 失敗 {len(errors)}"
    )
    for product_id, error in sorted(errors.items()):
        print(f"失敗 {product_id} {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
