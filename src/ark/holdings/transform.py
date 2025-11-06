"""Transformation utilities for ARK ETF holdings CSV."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Tuple

import pandas as pd

COLUMN_MAP = {
    "market_value_($)": "market_value",
    "market_value ($)": "market_value",
    "market_value_$": "market_value",
    "market_value": "market_value",
    "weight_(%)": "weight",
    "weight (%)": "weight",
    "weight%": "weight",
    "etf": "fund",
}

NUMERIC_COLUMNS = ("shares", "market_value", "weight", "average_cost", "price")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names to snake_case."""
    columns = []
    for raw in df.columns:
        key = raw.strip().lower()
        key = re.sub(r"[ /]", "_", key)
        key = COLUMN_MAP.get(key, key)
        columns.append(key)
    df = df.copy()
    df.columns = columns
    return df


def parse_numeric_series(series: pd.Series) -> pd.Series:
    """Strip common formatting characters and parse as float."""
    cleaned = (
        series.astype(str)
        .str.replace(r"[\$,()%]", "", regex=True)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace({"": None, "nan": None})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def clean_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for column in NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = parse_numeric_series(df[column])
    if "weight" in df.columns:
        df["weight"] = df["weight"] / 100.0
    return df


def parse_snapshot(df: pd.DataFrame) -> Tuple[pd.Timestamp, pd.DataFrame]:
    """Return normalised dataframe and snapshot date."""
    df = normalize_columns(df)
    if "date" not in df.columns:
        raise ValueError("CSV 缺少 date 列")
    as_of_raw = df["date"].iloc[0]
    as_of = pd.to_datetime(as_of_raw, format="%m/%d/%Y", errors="raise")
    df = clean_numeric_columns(df)
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    if "fund" in df.columns:
        df["fund"] = df["fund"].astype(str).str.strip().str.upper()
    return as_of, df
