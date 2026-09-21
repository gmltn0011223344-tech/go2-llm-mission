import asyncio
import unittest
from unittest import mock

import agent.mission_runner as mr
from agent.mission_runner import MissionRunner
from agent.sim_executor import SimExecutor
from agent.evaluation import GOLD_SCENARIOS, outcome, score

CMD = "A 지점으로 가서 병이 있는지 확인하고 돌아와"


def run(scripted=None, recover=True, **kw):
    ex = SimExecutor(scripted=scripted or {}, recover_on_retry=recover)
    return asyncio.run(MissionRunner(ex, **kw).run(CMD)), ex


class TestAutoAsk(unittest.TestCase):
    def test_normal_mission_completed(self):
        r, _ = run()
        self.assertEqual(r["status"], "MISSION_COMPLETED")

    def test_first_failure_is_auto_retry(self):
        r, _ = run({"A": "NO_PATH"})
        self.assertEqual((r["log"][0]["mode"], r["log"][0]["next_action"]), ("AUTO", "RETRY"))
        self.assertEqual(r["status"], "MISSION_COMPLETED")

    def test_repeated_failure_asks_and_waits(self):
        r, _ = run({"A": "NO_PATH"}, recover=False)
        self.assertEqual(r["status"], "ASK_PENDING")
        self.assertTrue(r["question"])

    def test_user_answer_return_home(self):
        async def ask(q):
            return "RETURN_HOME"
        r, _ = run({"BOTTLE": "TARGET_NOT_FOUND"}, recover=False, ask_user=ask)
        self.assertEqual(r["status"], "SAFE_RETURN")

    def test_unknown_user_answer_stops(self):
        async def ask(q):
            return "몰라"
        r, _ = run({"A": "NO_PATH"}, recover=False, ask_user=ask)
        self.assertEqual(r["status"], "STOPPED")

    def test_invalid_llm_waypoint_falls_back(self):
        bad = {"mode": "AUTO", "next_action": "MOVE_TO", "target": "A_ALT", "question": None, "reason": "우회"}
        with mock.patch.object(mr, "llm_next_action", return_value=bad):
            r, ex = run({"A": "NO_PATH"})
        self.assertNotIn("A_ALT", ex.seen)
        self.assertEqual(r["log"][0]["source"], "fallback")

    def test_error_stops_without_llm(self):
        with mock.patch.object(mr, "llm_next_action", side_effect=AssertionError("LLM 호출됨")):
            r, _ = run({"A": "ERROR"})
        self.assertEqual((r["status"], r["log"][0]["source"]), ("STOPPED", "safety"))

    def test_unregistered_destination_not_executed(self):
        ex = SimExecutor()
        r = asyncio.run(MissionRunner(ex).run("빨간 지점으로 가서 돌아와"))
        self.assertEqual(r["status"], "ASK_PENDING")
        self.assertEqual(ex.seen, {})

    def test_gold_table_rule_policy(self):
        runner = MissionRunner(None, decision_mode="rule")
        pairs = [(s["expected"], outcome(runner.decide(s["state"], s["ctx"]))) for s in GOLD_SCENARIOS]
        self.assertEqual(score(pairs)["correct"], len(GOLD_SCENARIOS))


if __name__ == "__main__":
    unittest.main()
