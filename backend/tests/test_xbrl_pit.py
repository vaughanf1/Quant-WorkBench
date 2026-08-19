"""The non-negotiable: a fundamental must resolve to what was KNOWN on a
date, not what it was later restated to.

Fixture models a real restatement shape (cf. Wells Fargo 2016 / GE 2018):
FY2018 revenue first reported as 1000 in the 10-K filed 2019-02-15, then
restated to 800 in a 10-K/A filed 2019-11-01.
"""
import pandas as pd

from app.data.xbrl_parser import as_of, flatten, fundamentals_as_of

FACTS = {
    "cik": 1,
    "entityName": "Test Co",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "label": "Revenues",
                "units": {
                    "USD": [
                        {"end": "2018-12-31", "val": 1000, "fy": 2018, "fp": "FY",
                         "form": "10-K", "filed": "2019-02-15", "accn": "a1"},
                        {"end": "2018-12-31", "val": 800, "fy": 2018, "fp": "FY",
                         "form": "10-K/A", "filed": "2019-11-01", "accn": "a2"},
                        {"end": "2019-12-31", "val": 1200, "fy": 2019, "fp": "FY",
                         "form": "10-K", "filed": "2020-02-20", "accn": "a3"},
                    ]
                },
            },
            "Assets": {
                "label": "Assets",
                "units": {
                    "USD": [
                        {"end": "2018-12-31", "val": 5000, "fy": 2018, "fp": "FY",
                         "form": "10-K", "filed": "2019-02-15", "accn": "a1"},
                    ]
                },
            },
        }
    },
}


def test_flatten_shape():
    df = flatten(FACTS)
    assert len(df) == 4
    assert set(df["concept"]) == {"Revenues", "Assets"}
    assert pd.api.types.is_datetime64_any_dtype(df["filed"])


def test_pit_before_restatement_sees_original():
    df = flatten(FACTS)
    snap = as_of(df, "2019-06-01", concept="Revenues")
    assert snap["val"].iloc[0] == 1000  # original, restatement not yet filed


def test_pit_after_restatement_sees_restated():
    df = flatten(FACTS)
    snap = as_of(df, "2020-01-01", concept="Revenues")
    # FY2019 not yet filed on this date; latest known period is FY2018,
    # now restated to 800.
    assert snap["end"].iloc[0] == pd.Timestamp("2018-12-31")
    assert snap["val"].iloc[0] == 800


def test_pit_picks_latest_period_once_available():
    df = flatten(FACTS)
    snap = as_of(df, "2020-06-01", concept="Revenues")
    assert snap["end"].iloc[0] == pd.Timestamp("2019-12-31")
    assert snap["val"].iloc[0] == 1200


def test_no_lookahead_returns_empty_before_any_filing():
    df = flatten(FACTS)
    assert as_of(df, "2019-01-01", concept="Revenues").empty


def test_fundamentals_as_of_dict():
    df = flatten(FACTS)
    snap = fundamentals_as_of(df, "2019-06-01")
    assert snap["revenue"] == 1000.0
    assert snap["total_assets"] == 5000.0
    assert snap["net_income"] is None  # not present -> None, not a guess


def test_flatten_empty_is_typed():
    df = flatten({"facts": {}})
    assert df.empty and "concept" in df.columns
