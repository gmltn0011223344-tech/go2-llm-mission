"""Simulated integration of Vision fields -> DB-shaped record -> Agent request -> reply.

Uses only local dictionaries; never calls teammate code or connects to Go2/SQLite/Ollama.
"""
import unittest
from integration.go2_contract import (
    ContractError, prepare_db_fields, prepare_agent_request, validate_agent_reply
)


class PatrolSmokeTest(unittest.TestCase):
    def test_six_observations_and_reobserve(self):
        route = ("P1_MAIN", "P1_SIDE", "P2_MAIN")
        observations = []
        for round_number in (1, 2):
            for point in route:
                # Inject a detection anomaly on the second visit to P1_SIDE.
                anomalous = round_number == 2 and point == "P1_SIDE"
                vision = {
                    "starfish_count": 0 if anomalous else 3,
                    "starfish_confidence": 0.38 if anomalous else 0.91,
                    "shell_count": 2,
                    "shell_confidence": 0.87,
                }
                db_row = prepare_db_fields(
                    point,
                    {"x": 2.0, "y": -1.0, "yaw": 0.0},
                    "GOAL_REACHED",
                    vision,
                )
                observations.append(db_row)

        self.assertEqual(len(observations), 6)
        self.assertEqual([o["point_id"] for o in observations], list(route) * 2)
        self.assertEqual(observations[4]["starfish_count"], 0)
        request = prepare_agent_request("mission-001", list(range(1, 7)))
        self.assertEqual(request["type"], "MISSION_COMPLETED")
        self.assertEqual(len(request["observation_ids"]), 6)

        # The reply is scripted, NOT a real LLM prediction.
        reply = {"request_id": "mission-001", "status": "ok", "decision": {
            "situation": "OBSERVATION_ANOMALY", "action": "REOBSERVE",
            "target_point": "P1_SIDE", "reason": "synthetic decrease with low confidence"
        }}
        result = validate_agent_reply(reply, request["request_id"])
        self.assertEqual(result["target_point"], "P1_SIDE")

        recovered = prepare_db_fields(
            "P1_SIDE", {"x": 2.0, "y": -1.0, "yaw": 0.0}, "GOAL_REACHED",
            {"starfish_count": 3, "starfish_confidence": 0.92,
             "shell_count": 2, "shell_confidence": 0.90}
        )
        observations.append(recovered)
        self.assertEqual(len(observations), 7)
        retry_request = prepare_agent_request(
            "retry-002", list(range(1, 8)),
            "REOBSERVATION_COMPLETED", "P1_SIDE",
        )
        self.assertEqual(retry_request["target_point"], "P1_SIDE")

        # Scripted recovery reply; doesn't prove actual LLM correctness.
        accepted = validate_agent_reply({
            "request_id": "retry-002", "status": "ok",
            "decision": {"situation": "NORMAL", "action": "CONTINUE",
                         "target_point": None, "reason": "synthetic baseline recovered"},
        }, "retry-002", reobservation=True)
        self.assertEqual(accepted["action"], "CONTINUE")

    def test_frame_failure_cannot_pass_as_zero(self):
        with self.assertRaises(ContractError):
            prepare_db_fields(
                "P1_MAIN", {"x": 1.0, "y": 0.0, "yaw": 0.0}, "GOAL_REACHED",
                {"starfish_count": None, "starfish_confidence": None,
                 "shell_count": None, "shell_confidence": None},
            )

    def test_bad_reply_target_blocked(self):
        request = prepare_agent_request("mission-003", list(range(1, 7)))
        with self.assertRaises(ContractError):
            validate_agent_reply({
                "request_id": request["request_id"], "status": "ok",
                "decision": {"situation": "OBSERVATION_ANOMALY",
                             "action": "REOBSERVE", "target_point": "UNKNOWN",
                             "reason": "scripted"},
            }, request["request_id"])


if __name__ == "__main__":
    unittest.main()
