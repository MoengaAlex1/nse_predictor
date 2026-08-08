"""
Tests for the archive-based corrector.

The guarantees that matter: it copies the archive's figures rather than scaling
the corrupt ones, it never invents a price, and it writes nothing without an
explicit flag.
"""
import json

import pytest

from pipeline.scripts.apply_archive_corrections import (
    build_corrections,
    classify,
    apply_corrections,
    restore,
)


def db(rows):
    return {"SMER": rows}


def ref(rows):
    return {"SMER": rows}


# --------------------------------------------------------------------------
# Copy, never scale
# --------------------------------------------------------------------------

def test_uses_the_archive_value_not_a_multiple_of_the_corrupt_one():
    """
    The real case: RTDB 0.36, archive 3.50. Scaling by ten gives 3.60 and is
    wrong. The archive figure must be copied verbatim.
    """
    cors = build_corrections(
        db({"2020-10-14": {"c": 0.36, "pc": 0.36}}),
        ref({"2020-10-14": {"c": 3.5, "pc": 3.5}}),
    )
    assert len(cors) == 1
    assert cors[0]["after"]["c"] == 3.5      # not 3.6


def test_all_price_fields_are_taken_from_the_archive():
    cors = build_corrections(
        db({"2020-01-02": {"c": 0.4, "h": 0.41, "l": 0.39, "pc": 0.4, "v": 10.0}}),
        ref({"2020-01-02": {"c": 4.0, "h": 4.1, "l": 3.9, "pc": 4.0, "v": 100.0}}),
    )
    after = cors[0]["after"]
    assert (after["c"], after["h"], after["l"], after["pc"], after["v"]) == \
           (4.0, 4.1, 3.9, 4.0, 100.0)


def test_derived_fields_are_recomputed_not_left_stale():
    """c - pc == ch holds on 100% of rows, so ch/pch must follow the new close."""
    cors = build_corrections(
        db({"2020-01-02": {"c": 0.4, "pc": 0.5, "ch": -0.1, "pch": -20.0}}),
        ref({"2020-01-02": {"c": 4.0, "pc": 5.0}}),
    )
    after = cors[0]["after"]
    assert after["ch"] == pytest.approx(-1.0)
    assert after["pch"] == pytest.approx(-20.0)


# --------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------

def test_dates_outside_archive_coverage_are_untouched():
    """Coverage ends 2025-10-31, so November 2025 must be left alone."""
    cors = build_corrections(
        db({"2025-11-11": {"c": 0.15}}),
        ref({"2025-10-31": {"c": 15.0}}),
    )
    assert cors == []


def test_a_no_trade_day_never_becomes_a_price():
    """Archive '-' parses to None; it must not be written as a close."""
    cors = build_corrections(
        db({"2020-01-02": {"c": 5.0}}),
        ref({"2020-01-02": {"c": None, "v": 0.0}}),
    )
    assert cors == []


def test_fields_absent_from_the_archive_keep_their_existing_value():
    cors = build_corrections(
        db({"2020-01-02": {"c": 0.4, "h": 9.9}}),
        ref({"2020-01-02": {"c": 4.0, "h": None}}),
    )
    assert cors[0]["after"]["h"] == 9.9


def test_matching_rows_produce_no_correction():
    cors = build_corrections(
        db({"2020-01-02": {"c": 4.0, "pc": 4.0}}),
        ref({"2020-01-02": {"c": 4.0, "pc": 4.0}}),
    )
    assert cors == []


# --------------------------------------------------------------------------
# Classification — keeps a targeted fix separate from a wholesale rebuild
# --------------------------------------------------------------------------

def test_classify_decimal_shift():
    c = {"changed": ["c"], "before": {"c": 0.4}, "after": {"c": 4.0}}
    assert classify(c) == "decimal"


def test_classify_minor_disagreement():
    c = {"changed": ["c"], "before": {"c": 4.9}, "after": {"c": 4.35}}
    assert classify(c) == "minor"


def test_classify_volume_only():
    c = {"changed": ["v"], "before": {"v": 1.0}, "after": {"v": 2.0}}
    assert classify(c) == "no_close"


# --------------------------------------------------------------------------
# Backup and restore
# --------------------------------------------------------------------------

class FakeRef:
    def __init__(self):
        self.writes = []

    def update(self, payload):
        self.writes.append(payload)


def test_backup_is_written_before_any_rtdb_call(tmp_path):
    """An interrupted run must still leave a complete record of the originals."""
    backup = tmp_path / "b.json"
    cors = [{"ticker": "SMER", "date": "2020-01-02",
             "before": {"c": 0.4}, "after": {"c": 4.0}, "changed": ["c"]}]
    ref_obj = FakeRef()
    apply_corrections(ref_obj, cors, str(backup))

    saved = json.loads(backup.read_text())
    assert saved["corrections"][0]["before"] == {"c": 0.4}
    assert ref_obj.writes == [{"prices/SMER/2020-01-02": {"c": 4.0}}]


def test_restore_puts_the_originals_back(tmp_path):
    backup = tmp_path / "b.json"
    backup.write_text(json.dumps({"corrections": [
        {"ticker": "SMER", "date": "2020-01-02", "before": {"c": 0.4}},
    ]}))
    ref_obj = FakeRef()
    assert restore(ref_obj, str(backup)) == 1
    assert ref_obj.writes == [{"prices/SMER/2020-01-02": {"c": 0.4}}]
