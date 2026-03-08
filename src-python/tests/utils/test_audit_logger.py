"""Tests for AuditLogger — immutable audit trail writer."""

import re

import pytest
from sqlalchemy import text

from app.utils.audit_logger import AuditLogger


@pytest.fixture
def logger(test_engine, monkeypatch):
    """AuditLogger backed by the test in-memory engine."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", test_engine)
    return AuditLogger()


class TestAuditLoggerLogChange:
    def test_writes_all_required_fields(self, logger, test_engine):
        logger.log_change(
            entity_type="asset",
            entity_id=1,
            action="CREATE",
        )

        with test_engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM audit_logs WHERE log_id = 1")).fetchone()

        assert row is not None
        assert row._mapping["entity_type"] == "asset"
        assert row._mapping["entity_id"] == 1
        assert row._mapping["action"] == "CREATE"
        assert row._mapping["actor"] == "system"

    def test_timestamp_is_iso8601_utc(self, logger, test_engine):
        logger.log_change(entity_type="config", entity_id=1, action="UPDATE")

        with test_engine.connect() as conn:
            ts = conn.execute(
                text("SELECT timestamp FROM audit_logs ORDER BY log_id DESC LIMIT 1")
            ).scalar()

        # Must match YYYY-MM-DDTHH:MM:SSZ
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ts
        ), f"Timestamp '{ts}' is not ISO 8601 UTC format"

    def test_update_records_field_and_values(self, logger, test_engine):
        logger.log_change(
            entity_type="asset",
            entity_id=5,
            action="UPDATE",
            field="historical_cost",
            old_value="1000.0000",
            new_value="1500.0000",
        )

        with test_engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM audit_logs ORDER BY log_id DESC LIMIT 1")
            ).fetchone()

        assert row._mapping["field"] == "historical_cost"
        assert row._mapping["old_value"] == "1000.0000"
        assert row._mapping["new_value"] == "1500.0000"

    def test_create_has_null_old_value(self, logger, test_engine):
        logger.log_change(
            entity_type="asset",
            entity_id=2,
            action="CREATE",
            new_value="laptop",
        )

        with test_engine.connect() as conn:
            row = conn.execute(
                text("SELECT old_value FROM audit_logs ORDER BY log_id DESC LIMIT 1")
            ).fetchone()

        assert row._mapping["old_value"] is None

    def test_append_only_multiple_calls(self, logger, test_engine):
        for i in range(3):
            logger.log_change(entity_type="asset", entity_id=i, action="UPDATE")

        with test_engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar()

        assert count == 3

    def test_custom_actor(self, logger, test_engine):
        logger.log_change(
            entity_type="config",
            entity_id=1,
            action="UPDATE",
            actor="admin",
        )

        with test_engine.connect() as conn:
            actor = conn.execute(
                text("SELECT actor FROM audit_logs ORDER BY log_id DESC LIMIT 1")
            ).scalar()

        assert actor == "admin"
