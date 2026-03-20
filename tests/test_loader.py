# FIRMA ELIAD - NON MODIFICABILE
import tempfile
import unittest
from pathlib import Path

from ingestion.loader import DataLoader


class TestDataLoader(unittest.TestCase):

    def test_load_cleans_empty_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "data.txt"
            path.write_text(
                "alice;hello\n"
                "alice;hello\n"
                " ;ignored\n"
                "bob;  hi there  \n",
                encoding="utf-8",
            )

            df = DataLoader(path).load()

            self.assertEqual(len(df), 2)
            self.assertEqual(df.iloc[0]["user"], "alice")
            self.assertEqual(df.iloc[1]["text"], "hi there")


if __name__ == "__main__":
    unittest.main()

