import io
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch


SAMPLE_CSV = """Date,Open,High,Low,Close,Volume,Is_Stale,Ticker
2024-01-02,28.0,28.5,27.5,28.2,1000000,0,SCOM
2024-01-03,28.2,28.8,28.0,28.6,1200000,0,SCOM
2024-01-04,28.6,29.0,28.3,28.9,900000,0,SCOM
"""


def test_build_records_extracts_all_fields():
    from pipeline.scripts.migrate_prices_to_rtdb import build_records
    df = pd.read_csv(io.StringIO(SAMPLE_CSV), parse_dates=["Date"])
    records = build_records(df)
    assert "2024-01-02" in records
    r = records["2024-01-02"]
    assert r["o"] == pytest.approx(28.0)
    assert r["c"] == pytest.approx(28.2)
    assert r["v"] == pytest.approx(1000000.0)


def test_build_records_skips_stale_rows():
    from pipeline.scripts.migrate_prices_to_rtdb import build_records
    csv = """Date,Open,High,Low,Close,Volume,Is_Stale,Ticker
2024-01-02,28.0,28.5,27.5,28.2,1000000,1,SCOM
2024-01-03,28.2,28.8,28.0,28.6,1200000,0,SCOM
"""
    df = pd.read_csv(io.StringIO(csv), parse_dates=["Date"])
    records = build_records(df, skip_stale=True)
    assert "2024-01-02" not in records
    assert "2024-01-03" in records


def test_build_records_computes_change():
    from pipeline.scripts.migrate_prices_to_rtdb import build_records
    df = pd.read_csv(io.StringIO(SAMPLE_CSV), parse_dates=["Date"])
    records = build_records(df)
    r = records["2024-01-03"]
    assert r["pc"] == pytest.approx(28.2, rel=1e-3)
    assert r["ch"] == pytest.approx(0.4, rel=1e-3)
    assert r["pch"] == pytest.approx(1.418, rel=1e-2)


def test_migrate_ticker_dry_run_no_writes():
    from pipeline.scripts.migrate_prices_to_rtdb import migrate_ticker
    import tempfile, os
    from pathlib import Path
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(SAMPLE_CSV)
        tmp_path = Path(f.name)
    try:
        root = MagicMock()
        count = migrate_ticker("SCOM", tmp_path, root, dry_run=True)
        assert count == 3
        root.update.assert_not_called()
    finally:
        os.unlink(tmp_path)
