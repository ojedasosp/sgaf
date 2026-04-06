"""Validators for maintenance event create and complete operations.

Returns list of {"field": "...", "message": "..."} dicts (empty list = valid).
Pattern mirrors asset_validator.py.
"""

import datetime
import re
from decimal import Decimal, InvalidOperation


_VALID_EVENT_TYPES = {"preventivo", "correctivo", "inspeccion"}
_VALID_COMPLETE_STATUSES = {"completed"}


def _is_valid_iso_date(value: str) -> bool:
    """Return True if value is a valid YYYY-MM-DD ISO date string."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        datetime.date.fromisoformat(value)
        return True
    except (ValueError, AttributeError):
        return False


def _is_valid_nonnegative_decimal(value: str) -> bool:
    """Return True if value parses as a non-negative Decimal (>= 0)."""
    try:
        d = Decimal(str(value))
        if d.is_nan() or d.is_infinite():
            return False
        return d >= 0
    except InvalidOperation:
        return False


def validate_maintenance_create(data: dict) -> list[dict]:
    """Validate a maintenance event creation payload.

    Required: asset_id, entry_date (stored as start_date).
    Optional: event_type, description, estimated_delivery_date, vendor.

    Returns list of validation errors (empty = valid).
    """
    errors: list[dict] = []

    # asset_id — required, positive int
    asset_id = data.get("asset_id")
    if asset_id is None:
        errors.append({"field": "asset_id", "message": "El ID del activo es obligatorio"})
    else:
        try:
            if int(asset_id) <= 0:
                raise ValueError
        except (ValueError, TypeError):
            errors.append({"field": "asset_id", "message": "El ID del activo debe ser un entero positivo"})

    # entry_date — required, valid ISO date
    entry_date = data.get("entry_date", "")
    if not entry_date or not str(entry_date).strip():
        errors.append({"field": "entry_date", "message": "La fecha de ingreso es obligatoria"})
    elif not _is_valid_iso_date(str(entry_date).strip()):
        errors.append({"field": "entry_date", "message": "Formato de fecha inválido (use AAAA-MM-DD)"})

    # event_type — optional, but must be one of allowed values if provided
    event_type = data.get("event_type")
    if event_type is not None and str(event_type).strip():
        if str(event_type).strip().lower() not in _VALID_EVENT_TYPES:
            errors.append({
                "field": "event_type",
                "message": "El tipo debe ser preventivo, correctivo o inspeccion",
            })

    # estimated_delivery_date — optional, valid ISO date if provided
    est_delivery = data.get("estimated_delivery_date")
    if est_delivery is not None and str(est_delivery).strip():
        if not _is_valid_iso_date(str(est_delivery).strip()):
            errors.append({
                "field": "estimated_delivery_date",
                "message": "Formato de fecha estimada de entrega inválido (use AAAA-MM-DD)",
            })

    # actual_delivery_date — optional, valid ISO date if provided
    act_delivery = data.get("actual_delivery_date")
    if act_delivery is not None and str(act_delivery).strip():
        if not _is_valid_iso_date(str(act_delivery).strip()):
            errors.append({
                "field": "actual_delivery_date",
                "message": "Formato de fecha real de entrega inválido (use AAAA-MM-DD)",
            })

    # actual_cost — optional, valid non-negative Decimal if provided
    act_cost = data.get("actual_cost")
    if act_cost is not None and str(act_cost).strip():
        if not _is_valid_nonnegative_decimal(str(act_cost).strip()):
            errors.append({
                "field": "actual_cost",
                "message": "El costo real debe ser un número válido mayor o igual a 0",
            })

    return errors


def validate_maintenance_complete(data: dict) -> list[dict]:
    """Validate a maintenance event completion/update payload.

    Required: status (must be "completed").
    Optional: actual_delivery_date, actual_cost, received_by, closing_observation.

    Returns list of validation errors (empty = valid).
    """
    errors: list[dict] = []

    # status — required, must be "completed"
    status = data.get("status")
    if not status or not str(status).strip():
        errors.append({"field": "status", "message": "El estado es obligatorio"})
    elif str(status).strip().lower() not in _VALID_COMPLETE_STATUSES:
        errors.append({
            "field": "status",
            "message": "El estado debe ser 'completed' para completar el evento",
        })

    # actual_delivery_date — optional, valid ISO date if provided
    act_delivery = data.get("actual_delivery_date")
    if act_delivery is not None and str(act_delivery).strip():
        if not _is_valid_iso_date(str(act_delivery).strip()):
            errors.append({
                "field": "actual_delivery_date",
                "message": "Formato de fecha real de entrega inválido (use AAAA-MM-DD)",
            })

    # actual_cost — optional, valid non-negative Decimal if provided
    act_cost = data.get("actual_cost")
    if act_cost is not None and str(act_cost).strip():
        if not _is_valid_nonnegative_decimal(str(act_cost).strip()):
            errors.append({
                "field": "actual_cost",
                "message": "El costo real debe ser un número válido mayor o igual a 0",
            })

    return errors
