"""Integration test: real MBODetector parsing (FakeModel) -> temporary SQLite -> Agent data contract.

No teammate code, robot device, model weights, or Ollama network connection is used.
"""
import sqlite3
import unittest
from datetime import datetime

from test_mbo_detector import make_detector, make_bgr_frame
from vision.mbo_detector import STATUS_OK, STATUS_FRAME_FAILED, to_observation
from integration.go2_contract import (
    ContractError, prepare_agent_request, prepare_db_fields, validate_agent_reply,
)


CREATE_TABLE = """
CREATE TABLE observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    point_id TEXT NOT NULL,
    robot_x REAL NOT NULL,
    robot_y REAL NOT NULL,
    robot_yaw REAL NOT NULL,
    navigation_state TEXT NOT NULL,
    starfish_count INTEGER,
    starfish_confidence REAL,
    shell_count INTEGER,
    shell_confidence REAL,
    situation TEXT,
    action TEXT,
    reason TEXT
)
"""


class ActualVisionSQLiteTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(CREATE_TABLE)

    def tearDown(self):
        self.conn.close()

    def insert_vision(self, point, detections):
        # Exercise the actual detector and to_observation implementation.
        detector = make_detector(detections=detections, blank_check=False)
        output = detector.detect(make_bgr_frame(), point_id=point)
        self.assertEqual(output["status"], STATUS_OK)
        fields = prepare_db_fields(
            point_id=point,
            pose={"x": 2.0, "y": -1.0, "yaw": 0.0},
            navigation_state="GOAL_REACHED",
            observation=to_observation(output),
        )
        cur = self.conn.execute(
            """INSERT INTO observations
            (timestamp, point_id, robot_x, robot_y, robot_yaw, navigation_state,
             starfish_count, starfish_confidence, shell_count, shell_confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(), *(fields[k] for k in (
                "point_id", "robot_x", "robot_y", "robot_yaw", "navigation_state",
                "starfish_count", "starfish_confidence", "shell_count", "shell_confidence"
            )))
        )
        self.conn.commit()
        return cur.lastrowid

    def history(self, point, exclude_id=None):
        if exclude_id is None:
            cursor = self.conn.execute(
                "SELECT * FROM observations WHERE point_id=? ORDER BY id DESC LIMIT ?",
                (point, 5))
        else:
            cursor = self.conn.execute(
                "SELECT * FROM observations WHERE point_id=? AND id != ? ORDER BY id DESC LIMIT ?",
                (point, exclude_id, 5))
        return [dict(row) for row in cursor.fetchall()]

    def test_real_detector_parsing_and_sqlite_roundtrip(self):
        starfish = (3, 0.91, [10, 20, 70, 90])
        scallop = (2, 0.87, [100, 20, 150, 85])
        route = ("P1_MAIN", "P1_SIDE", "P2_MAIN")
        ids = []
        for round_no in (1, 2):
            for point in route:
                anomaly = round_no == 2 and point == "P1_SIDE"
                detections = ([] if anomaly else
                              [starfish, starfish, starfish, scallop, scallop])
                ids.append(self.insert_vision(point, detections))
        self.assertEqual(len(ids), 6)
        self.assertEqual(len(set(ids)), 6)
        self.assertEqual(self.history("P1_SIDE")[0]["starfish_count"], 0)
        self.assertEqual(self.history("P1_SIDE")[1]["starfish_count"], 3)

        req = prepare_agent_request("m-1", ids)
        self.assertEqual(req["observation_ids"], ids)
        # The next decision is scripted, NOT produced by an LLM.
        decision = validate_agent_reply({
            "request_id": "m-1", "status": "ok",
            "decision": {"situation": "OBSERVATION_ANOMALY",
                         "action": "REOBSERVE", "target_point": "P1_SIDE",
                         "reason": "scripted observation difference"},
        }, "m-1")
        self.assertEqual(decision["action"], "REOBSERVE")

        reobs_id = self.insert_vision(
            "P1_SIDE", [starfish, starfish, starfish, scallop, scallop]
        )
        self.assertEqual(len(self.history("P1_SIDE", exclude_id=reobs_id)), 2)
        self.assertEqual(self.history("P1_SIDE")[0]["starfish_count"], 3)
        self.assertEqual(self.history("P1_SIDE")[1]["starfish_count"], 0)
        followup = prepare_agent_request(
            "m-2", ids + [reobs_id], "REOBSERVATION_COMPLETED", "P1_SIDE")
        self.assertEqual(len(followup["observation_ids"]), 7)
        final = validate_agent_reply({
            "request_id": "m-2", "status": "ok",
            "decision": {"situation": "NORMAL", "action": "CONTINUE",
                         "target_point": None, "reason": "scripted baseline recovered"},
        }, "m-2", reobservation=True)
        self.assertEqual(final["action"], "CONTINUE")

    def test_failed_frame_is_not_inserted_as_zero(self):
        detector = make_detector()
        result = detector.detect(None)
        self.assertEqual(result["status"], STATUS_FRAME_FAILED)
        with self.assertRaises(ContractError):
            prepare_db_fields(
                "P1_MAIN", {"x": 1.0, "y": 2.0, "yaw": 0.0},
                "GOAL_REACHED", to_observation(result))
        count = self.conn.execute("SELECT count(*) FROM observations").fetchone()[0]
        self.assertEqual(count, 0)

    def test_sql_parameterized_history(self):
        self.insert_vision("P1_MAIN", [])
        self.insert_vision("P2_MAIN", [])
        self.assertEqual(len(self.history("P1_MAIN")), 1)
        self.assertEqual(len(self.history("P2_MAIN")), 1)
        self.assertEqual(len(self.history("P1_MAIN' OR 1=1 --")), 0)


if __name__ == "__main__":
    unittest.main()
