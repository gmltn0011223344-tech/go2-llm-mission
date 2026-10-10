"""Read-only contract helpers for integration with daryung/go2_capstone.

These functions do not control a robot, access SQLite, or call an LLM.
The teammate's repository is an external interface reference, not a dependency.
"""
from __future__ import annotations

import math
from typing import Any

POINTS = ("P1_MAIN", "P1_SIDE", "P2_MAIN")
STATES = {"NORMAL", "OBSERVATION_ANOMALY", "POSSIBLE_REAL_CHANGE", "NAVIGATION_FAILURE"}
ACTIONS = {"CONTINUE", "REOBSERVE", "CHANGE_VIEWPOINT", "RETRY_NAVIGATION", "ACCEPT_CHANGE", "ABORT"}
SAVE_FIELDS = ("point_id", "robot_x", "robot_y", "robot_yaw", "navigation_state",
               "starfish_count", "starfish_confidence", "shell_count", "shell_confidence")


class ContractError(ValueError):
    """Integration data violates the agreed interface."""


def prepare_db_fields(point_id: str, pose: dict, navigation_state: str, observation: dict) -> dict:
    """Build keyword arguments for teammate's save_observation(...).

    observation is the four-field output of vision.mbo_detector.to_observation().
    Never convert FRAME_FAILED / INFERENCE_FAILED into zero detected organisms.
    No database write happens here.
    """
    if point_id not in POINTS:
        raise ContractError("Unknown observation point")
    if not isinstance(pose, dict):
        raise ContractError("pose must be a mapping")
    if not isinstance(navigation_state, str) or not navigation_state:
        raise ContractError("navigation_state is required")
    if not isinstance(observation, dict):
        raise ContractError("observation must be a mapping")
    fields = ("starfish_count", "starfish_confidence", "shell_count", "shell_confidence")
    if any(k not in observation for k in fields):
        raise ContractError("Missing Vision observation field")
    # The current teammate DB interface does not safely represent Vision failures.
    if any(observation[k] is None for k in fields):
        raise ContractError("Vision failed or produced missing values: do not store as zero")
    for key in ("x", "y", "yaw"):
        value = pose.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ContractError("Invalid pose coordinate: " + key)
    for key in ("starfish_count", "shell_count"):
        val = observation[key]
        if type(val) is not int or val < 0:
            raise ContractError("Invalid object count: " + key)
    for key in ("starfish_confidence", "shell_confidence"):
        val = observation[key]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or not 0 <= val <= 1:
            raise ContractError("Invalid confidence: " + key)
    return {
        "point_id": point_id,
        "robot_x": float(pose["x"]),
        "robot_y": float(pose["y"]),
        "robot_yaw": float(pose["yaw"]),
        "navigation_state": navigation_state,
        **{key: observation[key] for key in fields},
    }


def prepare_agent_request(request_id: str, observation_ids: list[int],
                          request_type: str = "MISSION_COMPLETED",
                          target_point: str | None = None) -> dict:
    """Make test_scenario1.py -> reciver.py request payload (JSON-serializable).

    Six ordered observation IDs for MISSION_COMPLETED, seven for REOBSERVATION_COMPLETED.
    IDs refer to rows already saved by the robot-side SQLite process.
    """
    if not isinstance(request_id, str) or not request_id.strip():
        raise ContractError("request_id must be a nonempty string")
    sizes = {"MISSION_COMPLETED": 6, "REOBSERVATION_COMPLETED": 7}
    if request_type not in sizes:
        raise ContractError("Unsupported request type")
    if not isinstance(observation_ids, list) or len(observation_ids) != sizes[request_type]:
        raise ContractError("Incorrect observation ID count")
    if any(type(i) is not int or i <= 0 for i in observation_ids) or len(set(observation_ids)) != len(observation_ids):
        raise ContractError("IDs must be distinct positive integers")
    if request_type == "REOBSERVATION_COMPLETED":
        if target_point not in POINTS:
            raise ContractError("Reobservation needs a registered target_point")
    elif target_point is not None:
        raise ContractError("Unexpected target_point for mission completion")
    output = {"request_id": request_id, "type": request_type,
              "observation_ids": observation_ids, "route": list(POINTS)}
    if target_point is not None:
        output["target_point"] = target_point
    return output


def validate_agent_reply(reply: dict, request_id: str, *, reobservation: bool = False) -> dict:
    """Check worker response envelope and conservatively allow robot-side actions.

    The current teammate receiver allows CONTINUE/REOBSERVE on normal completion
    and additionally ACCEPT_CHANGE after reobservation. This checks that subset,
    not every action the LLM schema is capable of generating.
    """
    if not isinstance(reply, dict) or reply.get("request_id") != request_id:
        raise ContractError("Reply request_id mismatch (stale or unrelated decision)")
    if reply.get("status") != "ok":
        raise ContractError("Agent reported failure")
    decision = reply.get("decision")
    if not isinstance(decision, dict):
        raise ContractError("Missing decision object")
    if set(decision) != {"situation", "action", "target_point", "reason"}:
        raise ContractError("Decision schema mismatch")
    if decision["situation"] not in STATES:
        raise ContractError("Unknown situation")
    allowed = {"CONTINUE", "REOBSERVE", "ACCEPT_CHANGE"} if reobservation else {"CONTINUE", "REOBSERVE"}
    if decision["action"] not in allowed:
        raise ContractError("Action unsupported by current robot recovery route")
    if decision["action"] == "REOBSERVE":
        if decision["target_point"] not in POINTS:
            raise ContractError("REOBSERVE requires registered target")
    elif decision["target_point"] is not None:
        raise ContractError("Non-REOBSERVE actions must have null target_point")
    if not isinstance(decision["reason"], str) or not decision["reason"].strip():
        raise ContractError("Decision reason is required")
    return decision
