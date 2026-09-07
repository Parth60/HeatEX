from __future__ import annotations

from datetime import datetime, timezone
import json


PROJECT_SCHEMA = "hxrace.project.v1"


def build_project_snapshot(
    *,
    project_name: str,
    engineer: str,
    notes: str,
    display_units: str,
    ui_state: dict,
    report_payload: dict | None,
) -> dict:
    return {
        "schema": PROJECT_SCHEMA,
        "saved_utc": datetime.now(timezone.utc).isoformat(),
        "project": {
            "name": project_name.strip() or "HX-RACE Project",
            "engineer": engineer.strip(),
            "notes": notes.strip(),
            "display_units": display_units,
        },
        "ui_state": ui_state,
        "engineering_record": report_payload,
        "restore_scope": (
            "Core shell-and-tube, thermodynamic, geometry, Bell-Delaware and "
            "mechanical widget values are restorable. Calculated results are "
            "retained as an engineering record and are recalculated after restore."
        ),
    }


def project_to_bytes(project: dict) -> bytes:
    return json.dumps(
        project,
        indent=2,
        default=str,
    ).encode("utf-8")


def parse_project_bytes(data: bytes) -> dict:
    try:
        project = json.loads(data.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Project JSON could not be parsed: {exc}") from exc

    if not isinstance(project, dict):
        raise ValueError("Project file must contain a JSON object.")

    if project.get("schema") != PROJECT_SCHEMA:
        raise ValueError(
            f"Unsupported project schema '{project.get('schema')}'. "
            f"Expected '{PROJECT_SCHEMA}'."
        )

    if not isinstance(project.get("ui_state"), dict):
        raise ValueError("Project file does not contain a valid ui_state object.")

    return project
