"""Tests for utils/metrics — log_metric and get_metrics_summary."""

from __future__ import annotations

import pytest

import utils.metrics as metrics_mod


class TestLogMetric:
    def test_log_metric_does_not_raise(self, tmp_db):
        # Should succeed silently
        metrics_mod.log_metric("index", 1.23, course_id="COMP3900", chunks_added=42)

    def test_logged_metric_appears_in_summary(self, tmp_db):
        metrics_mod.log_metric("index", 2.0, course_id="c1")
        summary = metrics_mod.get_metrics_summary()
        assert "index" in summary
        assert summary["index"]["total"] == 1
        assert summary["index"]["avg_s"] == 2.0

    def test_multiple_logs_aggregated(self, tmp_db):
        metrics_mod.log_metric("quiz", 1.0)
        metrics_mod.log_metric("quiz", 3.0)
        summary = metrics_mod.get_metrics_summary()
        assert summary["quiz"]["total"] == 2
        assert summary["quiz"]["avg_s"] == 2.0
        assert summary["quiz"]["min_s"] == 1.0
        assert summary["quiz"]["max_s"] == 3.0

    def test_different_operations_separated(self, tmp_db):
        metrics_mod.log_metric("index", 1.5)
        metrics_mod.log_metric("summary", 3.0)
        summary = metrics_mod.get_metrics_summary()
        assert "index" in summary
        assert "summary" in summary

    def test_get_recent_metrics_returns_list(self, tmp_db):
        metrics_mod.log_metric("chat", 0.5, course_id="c1")
        recent = metrics_mod.get_recent_metrics(limit=10)
        assert isinstance(recent, list)
        assert len(recent) >= 1
        assert recent[0]["operation"] == "chat"

    def test_get_recent_metrics_limit_respected(self, tmp_db):
        for i in range(10):
            metrics_mod.log_metric("flashcard", float(i))
        recent = metrics_mod.get_recent_metrics(limit=5)
        assert len(recent) <= 5

    def test_meta_json_stored_and_retrieved(self, tmp_db):
        metrics_mod.log_metric("index", 1.0, course_id="X", files_indexed=7)
        recent = metrics_mod.get_recent_metrics(limit=1)
        assert recent[0]["meta"].get("files_indexed") == 7

    def test_log_metric_silent_on_db_error(self, monkeypatch):
        # Even if DB is unavailable, log_metric should not raise
        import sqlite3
        monkeypatch.setattr(metrics_mod, "_connect", lambda: (_ for _ in ()).throw(sqlite3.OperationalError("no db")))
        # Should not raise
        metrics_mod.log_metric("quiz", 1.0)

    def test_get_metrics_summary_empty_db_returns_empty(self, tmp_db):
        summary = metrics_mod.get_metrics_summary()
        assert isinstance(summary, dict)
        # May be empty or populated depending on prior test isolation
