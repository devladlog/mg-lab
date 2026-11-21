"""Three ways to hold data out. They answer different questions, and only one of them matches how the model will be used."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from .data import GROUP, TARGET, TIME


def random_split(df: pd.DataFrame, test_size: float = 0.25, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rows at random (stratified on the target). Fine only if rows are independent: here the same employee is in both halves."""
    tr, te = train_test_split(df, test_size=test_size, random_state=seed, stratify=df[TARGET])
    return tr, te


def group_split(df: pd.DataFrame, test_size: float = 0.25, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Whole requesters go to one side: the test set is made of employees the model has never seen."""
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    i, j = next(gss.split(df, groups=df[GROUP]))
    return df.iloc[i], df.iloc[j]


def time_split(df: pd.DataFrame, test_fraction: float = 0.25) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The oldest days train, the newest days test: how the model will really be used."""
    cut = np.quantile(df[TIME], 1 - test_fraction)
    return df[df[TIME] < cut], df[df[TIME] >= cut]


def overlap(a: pd.DataFrame, b: pd.DataFrame, column: str = GROUP) -> int:
    """Number of identifiers present on both sides. Must be 0 for a group split."""
    return len(set(a[column]) & set(b[column]))
