import csv
import io
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import book_list  # noqa: E402


HEADER = [
    "ProductID",
    "一覧No",
    "タイトル",
    "タイトル状態",
    "サブタイトル・シリーズ",
    "著者",
    "出版社",
    "底本刊行",
    "ISBN",
    "eISBN",
    "code",
    "status",
    "pdf",
    "pages",
    "captured_at",
    "note",
    "収録元",
    "不足項目",
    "次の作業",
]


def write_list(path: Path, rows: list[dict[str, str]], newline_at_end: bool = True) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=HEADER, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    text = buffer.getvalue()
    if not newline_at_end:
        text = text.rstrip("\n")
    path.write_bytes(text.encode("utf-8-sig"))


def read_list(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class AddProductIdsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(self.id().replace(".", "_") + ".csv")
        # Keep the fixture next to the test only for the duration of the test.
        self.path = Path("/tmp") / self.path.name
        write_list(
            self.path,
            [
                {
                    "ProductID": "KP00071054",
                    "一覧No": "1",
                    "タイトル": "ハエトリグモハンドブック 増補改訂版",
                    "タイトル状態": "検索リスト",
                    "サブタイトル・シリーズ": "",
                    "著者": "須黒達巳",
                    "出版社": "文一総合出版",
                    "底本刊行": "2022-04",
                    "ISBN": "9784829981696",
                    "eISBN": "9784829955635",
                    "code": "library.pref.hokkaido",
                    "status": "取得済",
                    "pdf": "capture_20260921_KP00071054.pdf",
                    "pages": "156",
                    "captured_at": "2026-09-21",
                    "note": "",
                    "収録元": "検索リスト+取得台帳",
                    "不足項目": "",
                    "次の作業": "対応不要",
                }
            ],
        )
        self.original = self.path.read_bytes()

    def tearDown(self) -> None:
        self.path.unlink(missing_ok=True)

    def test_adds_new_id_without_rewriting_existing_rows(self) -> None:
        results, rejected = book_list.add_product_ids(self.path, ["KP00099999"])

        self.assertEqual(rejected, [])
        self.assertEqual(results, [book_list.AddResult("KP00099999", "added", status="未取得")])
        updated = self.path.read_bytes()
        self.assertTrue(updated.startswith(self.original))
        rows = read_list(self.path)
        self.assertEqual([row["ProductID"] for row in rows], ["KP00071054", "KP00099999"])
        added = rows[1]
        self.assertEqual(added["status"], "未取得")
        self.assertEqual(added["タイトル"], "")
        self.assertEqual(added["captured_at"], "")
        self.assertEqual(added["pages"], "")

    def test_existing_id_is_not_added_again(self) -> None:
        results, rejected = book_list.add_product_ids(
            self.path,
            ["https://kinoden.kinokuniya.co.jp/hokkaido/bookdetail/p/KP00071054/"],
        )

        self.assertEqual(rejected, [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].action, "existing")
        self.assertEqual(results[0].product_id, "KP00071054")
        self.assertEqual(results[0].title, "ハエトリグモハンドブック 増補改訂版")
        self.assertEqual(results[0].status, "取得済")
        self.assertEqual(results[0].captured_at, "2026-09-21")
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_fullwidth_and_unpadded_id_match_existing_row(self) -> None:
        results, _ = book_list.add_product_ids(self.path, ["ＫＰ７１０５４"])

        self.assertEqual(results[0].action, "existing")
        self.assertEqual(results[0].product_id, "KP00071054")
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_second_copy_in_the_same_command_is_a_duplicate(self) -> None:
        results, rejected = book_list.add_product_ids(
            self.path,
            ["KP00012345", "https://example.test/bookdetail/p/KP00012345/"],
        )

        self.assertEqual(rejected, [])
        self.assertEqual([result.action for result in results], ["added", "existing"])
        self.assertEqual([row["ProductID"] for row in read_list(self.path) if row["ProductID"] == "KP00012345"], ["KP00012345"])

    def test_token_without_id_does_not_change_the_file(self) -> None:
        results, rejected = book_list.add_product_ids(self.path, ["ハエトリグモ"])

        self.assertEqual(results, [])
        self.assertEqual(rejected, [book_list.RejectedToken("ハエトリグモ")])
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_appends_after_a_file_that_has_no_trailing_newline(self) -> None:
        write_list(
            self.path,
            [
                {
                    "ProductID": "KP00071054",
                    "タイトル": "ハエトリグモハンドブック 増補改訂版",
                    "status": "取得済",
                    "captured_at": "2026-09-21",
                    **{name: "" for name in HEADER if name not in {"ProductID", "タイトル", "status", "captured_at"}},
                }
            ],
            newline_at_end=False,
        )

        book_list.add_product_ids(self.path, ["KP00012345"])
        rows = read_list(self.path)
        self.assertEqual([row["ProductID"] for row in rows], ["KP00071054", "KP00012345"])

    def test_cli_prints_existing_row_and_exits_zero(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "book_list.py"), "--list", str(self.path), "add", "KP00071054"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("既存  KP00071054", completed.stdout)
        self.assertIn("ハエトリグモハンドブック 増補改訂版", completed.stdout)
        self.assertIn("取得済", completed.stdout)
        self.assertIn("2026-09-21", completed.stdout)
        self.assertEqual(self.path.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
