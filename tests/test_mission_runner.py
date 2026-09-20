import asyncio
import unittest

from agent.mission_runner import MissionRunner
from agent.sim_executor import SimExecutor


COMMAND = "빨간 지점을 지나 파란 지점에서 노트북이 있는지 확인하고 돌아와"


class MissionRunnerTests(unittest.TestCase):
    def run_mission(self, executor, mode="rule", **kwargs):
        runner = MissionRunner(executor, decision_mode=mode, **kwargs)
        return asyncio.run(runner.run(COMMAND))

    def test_normal_mission_completes(self):
        result = self.run_mission(SimExecutor())
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "MISSION_COMPLETED")

    def test_failed_observation_then_home_is_not_success(self):
        executor = SimExecutor(
            scripted={"LAPTOP": "TARGET_NOT_FOUND"},
            recover_on_retry=False,
        )
        result = self.run_mission(executor, mode="rule")
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "SAFE_RETURN")

    def test_invalid_llm_waypoint_falls_back_to_rule(self):
        executor = SimExecutor(scripted={"BLUE": "NO_PATH"})
        result = self.run_mission(executor, mode="llm")
        fallback_logs = [row for row in result["log"] if row["fallback_used"]]
        self.assertTrue(fallback_logs)
        self.assertEqual(fallback_logs[0]["next_action"], "RETRY")


if __name__ == "__main__":
    unittest.main()
