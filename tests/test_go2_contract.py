"""Pure standard-library integration contract tests; no robot, DB or Ollama required."""
import unittest

from integration.go2_contract import (
    ContractError, POINTS, SAVE_FIELDS,
    prepare_agent_request, prepare_db_fields, validate_agent_reply,
)

OBS = {"starfish_count": 2, "starfish_confidence": 0.73,
       "shell_count": 1, "shell_confidence": 0.40}
POSE = {"x": 2.4, "y": -1.3, "yaw": 0.0}


class ObservationContractTest(unittest.TestCase):
    def test_db_signature_matches(self):
        value = prepare_db_fields("P1_MAIN", POSE, "GOAL_REACHED", OBS)
        self.assertEqual(set(value), set(SAVE_FIELDS))
        self.assertEqual(value["starfish_count"], 2)

    def test_zero_is_valid_detection(self):
        data = dict(OBS, starfish_count=0, starfish_confidence=0.0)
        self.assertEqual(prepare_db_fields("P1_SIDE", POSE, "GOAL_REACHED", data)["starfish_count"], 0)

    def test_missing_observation_must_not_become_zero(self):
        with self.assertRaises(ContractError):
            prepare_db_fields("P1_MAIN", POSE, "GOAL_REACHED", dict(OBS, starfish_count=None))

    def test_invalid_point(self):
        with self.assertRaises(ContractError):
            prepare_db_fields("P1_ALT", POSE, "GOAL_REACHED", OBS)

    def test_invalid_confidence(self):
        with self.assertRaises(ContractError):
            prepare_db_fields("P1_MAIN", POSE, "GOAL_REACHED", dict(OBS, shell_confidence=1.3))

    def test_invalid_pose(self):
        with self.assertRaises(ContractError):
            prepare_db_fields("P1_MAIN", {"x": float("nan"), "y": 0, "yaw": 0}, "GOAL_REACHED", OBS)

    def test_missing_field(self):
        bad = dict(OBS)
        del bad["shell_count"]
        with self.assertRaises(ContractError):
            prepare_db_fields("P1_MAIN", POSE, "GOAL_REACHED", bad)


class AgentContractTest(unittest.TestCase):
    def test_six_ids(self):
        req = prepare_agent_request("req-1", [1, 2, 3, 4, 5, 6])
        self.assertEqual(req["type"], "MISSION_COMPLETED")
        self.assertEqual(req["route"], list(POINTS))

    def test_seven_ids_with_target(self):
        req = prepare_agent_request("req-2", list(range(1, 8)),
                                    "REOBSERVATION_COMPLETED", "P1_SIDE")
        self.assertEqual(req["target_point"], "P1_SIDE")

    def test_duplicate_ids_blocked(self):
        with self.assertRaises(ContractError):
            prepare_agent_request("req-3", [1, 2, 3, 4, 5, 5])

    def test_bad_recovery_target_blocked(self):
        with self.assertRaises(ContractError):
            prepare_agent_request("req-4", list(range(1, 8)),
                                  "REOBSERVATION_COMPLETED", "P2_SIDE")

    def test_good_reply(self):
        reply = {"request_id": "req-5", "status": "ok",
                 "decision": {"situation": "OBSERVATION_ANOMALY",
                              "action": "REOBSERVE", "target_point": "P1_MAIN",
                              "reason": "low confidence"}}
        self.assertEqual(validate_agent_reply(reply, "req-5")["action"], "REOBSERVE")

    def test_old_reply_blocked(self):
        reply = {"request_id": "previous", "status": "ok",
                 "decision": {"situation": "NORMAL", "action": "CONTINUE",
                              "target_point": None, "reason": "stable"}}
        with self.assertRaises(ContractError):
            validate_agent_reply(reply, "current")

    def test_unsupported_action_blocked(self):
        reply = {"request_id": "req-6", "status": "ok",
                 "decision": {"situation": "NORMAL", "action": "CHANGE_VIEWPOINT",
                              "target_point": "P1_MAIN", "reason": "different angle"}}
        with self.assertRaises(ContractError):
            validate_agent_reply(reply, "req-6")

    def test_accept_change_only_after_reobservation(self):
        reply = {"request_id": "req-7", "status": "ok",
                 "decision": {"situation": "POSSIBLE_REAL_CHANGE", "action": "ACCEPT_CHANGE",
                              "target_point": None, "reason": "confirmed"}}
        with self.assertRaises(ContractError):
            validate_agent_reply(reply, "req-7")
        self.assertEqual(validate_agent_reply(reply, "req-7", reobservation=True)["action"],
                         "ACCEPT_CHANGE")


if __name__ == "__main__":
    unittest.main()
