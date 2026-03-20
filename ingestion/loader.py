# FIRMA ELIAD - NON MODIFICABILE
from pathlib import Path

import pandas as pd
from loguru import logger


class DataLoader:

    def __init__(self, file_path):
        self.file_path = Path(file_path)

    def _read_with_fallback_encodings(self):
        encodings = ["utf-8", "latin-1"]
        errors = []

        for encoding in encodings:
            try:
                df = pd.read_csv(
                    self.file_path,
                    sep=";",
                    names=["user", "text"],
                    encoding=encoding,
                    dtype={"user": "string", "text": "string"},
                    on_bad_lines="warn",
                )
                logger.info(f"Loaded file with encoding: {encoding}")
                return df
            except Exception as exc:
                errors.append(f"{encoding}: {exc}")

        joined = " | ".join(errors)
        raise ValueError(f"Unable to parse input file. Tried encodings -> {joined}")

    def load(self):
        if not self.file_path.exists():
            raise FileNotFoundError(f"Dataset not found: {self.file_path}")

        df = self._read_with_fallback_encodings()

        rows_loaded = len(df)

        df["user"] = df["user"].fillna("").str.strip()
        df["text"] = df["text"].fillna("").str.strip()

        empty_mask = (df["user"] == "") | (df["text"] == "")
        n_empty = int(empty_mask.sum())
        if n_empty:
            logger.warning(f"Dropped {n_empty} empty/invalid rows out of {rows_loaded} loaded")
        df = df[~empty_mask]

        n_before_dedup = len(df)
        df = df.drop_duplicates().reset_index(drop=True)
        n_duplicates = n_before_dedup - len(df)
        if n_duplicates:
            logger.warning(f"Removed {n_duplicates} duplicate rows")

        logger.info(f"Dataset ready: {len(df)} valid rows (loaded {rows_loaded}, dropped {n_empty} empty, {n_duplicates} duplicates)")

        if df.empty:
            raise ValueError("Dataset is empty after cleaning. Provide valid 'user;text' records.")

        return df

