"""Audit trail writer for SGAF.

AuditLogger is the ONLY permitted path to write to audit_logs.
Direct INSERT to audit_logs is forbidden at every layer.
"""

from datetime import datetime, timezone

from sqlalchemy import insert

from app.database import get_db
from app.models.tables import audit_logs


class AuditLogger:
    """Write immutable audit entries to audit_logs.

    Usage:
        logger = AuditLogger()
        logger.log_change(
            entity_type="asset",
            entity_id=1,
            action="UPDATE",
            field="historical_cost",
            old_value="1200.0000",
            new_value="1500.0000",
        )
    """

    def log_change(
        self,
        entity_type: str,
        entity_id: int,
        action: str,
        field: str | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
        actor: str = "system",
    ) -> None:
        """Write an immutable audit entry.

        Args:
            entity_type: "asset" | "maintenance_event" | "config"
            entity_id: Primary key of the affected entity.
            action: "CREATE" | "UPDATE" | "RETIRE" | "DELETE" | "LOGIN"
            field: Column name changed (None for CREATE/RETIRE/DELETE).
            old_value: Previous value as string (None for CREATE).
            new_value: New value as string (None for DELETE).
            actor: Who performed the action (default "system" for MVP).
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        stmt = insert(audit_logs).values(
            timestamp=timestamp,
            actor=actor,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            field=field,
            old_value=old_value,
            new_value=new_value,
        )
        with get_db() as conn:
            conn.execute(stmt)
            conn.commit()
