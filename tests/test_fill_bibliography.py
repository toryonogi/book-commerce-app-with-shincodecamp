import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fill_bibliography  # noqa: E402


class ApplyBibliographyTest(unittest.TestCase):
    def test_fills_only_empty_cells(self) -> None:
        row = ["", "KP00001851", "", "取得済", "森林資源の環境経済史", "", "", "", "320"]
        info = {
            "title": "別のタイトル",
            "author": "山口明日香",
            "publisher": "慶應義塾大学出版会",
            "isbn": "9784766422429",
        }

        updated = fill_bibliography.apply_bibliography(row, info)

        self.assertEqual(updated[4], "森林資源の環境経済史")
        self.assertEqual(updated[5], "山口明日香")
        self.assertEqual(updated[6], "慶應義塾大学出版会")
        self.assertEqual(updated[7], "9784766422429")
        self.assertEqual(updated[8], "320")

    def test_joins_authors_and_ignores_blank_api_values(self) -> None:
        info = fill_bibliography.bibliography_from_bookinfo(
            {"title": "モグラハンドブック", "author": ["飯島正広", "土屋公幸"], "publisher": "文一総合出版", "isbn": ""}
        )
        updated = fill_bibliography.apply_bibliography(["", "KP00053694", "", "", "", "", "", ""], info)

        self.assertEqual(updated[4], "モグラハンドブック")
        self.assertEqual(updated[5], "飯島正広 土屋公幸")
        self.assertEqual(updated[6], "文一総合出版")
        self.assertEqual(updated[7], "")

    def test_product_ids_with_gaps_skips_complete_rows_and_rows_without_id(self) -> None:
        rows = [
            ["", "KP00000001", "", "未取得", "題名", "著者", "出版社", "9780000000000"],
            ["", "KP00000002", "", "未取得", "題名", "", "", ""],
            ["", "", "", "取得済", "ファイル名だけ", "", "", ""],
        ]

        self.assertEqual(fill_bibliography.product_ids_with_gaps(rows), ["KP00000002"])


if __name__ == "__main__":
    unittest.main()
