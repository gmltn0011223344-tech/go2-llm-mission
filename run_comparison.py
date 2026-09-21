"""
run_comparison.py  (참고용 — 핵심 평가는 run_auto_ask_eval.py)

2026-09-21 방향 변경으로 Rule vs LLM 비교는 핵심 평가가 아닙니다.
시뮬레이터 좌표(RED/BLUE)를 임시 허용해 기존 비교 흐름만 남겨 둡니다.

로봇 없이 시뮬레이터로 같은 시나리오를 Rule 방식과 LLM 방식으로 각각 돌려
결과를 비교합니다. 발표의 핵심 근거(= "왜 LLM이 필요한가")를 만드는 스크립트.

    python3 run_comparison.py

- ANTHROPIC_API_KEY가 있으면 진짜 LLM, 없으면 mock으로 동작(안내 문구 출력).
- 결과는 화면 + comparison_result.csv 로 저장.
"""

import asyncio
import csv
from agent.mission_runner import MissionRunner
from agent.sim_executor import SimExecutor

SIM_WAYPOINTS = {"RED", "BLUE", "HOME"}
COMMAND = "빨간 지점을 지나 파란 지점에서 노트북이 있는지 확인하고 돌아와"

# 시나리오: 특정 목표에서 어떤 예외를 강제로 낼지
SCENARIOS = [
    {"name": "정상",          "scripted": {}},
    {"name": "경로차단(BLUE)", "scripted": {"BLUE": "NO_PATH"}},
    {"name": "시간초과(BLUE)", "scripted": {"BLUE": "TIMEOUT"}},
    {"name": "물체없음(노트북)", "scripted": {"LAPTOP": "TARGET_NOT_FOUND"}},
]


def decisions_str(result):
    """로그의 각 스텝을 '상태→결정' 한 줄로 이어붙임 (방식 간 차이를 한눈에)."""
    parts = []
    for e in result["log"]:
        parts.append(f"{e['state']}→{e['next_action'] or 'ASK'}"
                     + (f":{e['next_target']}" if e.get("next_target") else ""))
    return " | ".join(parts)


async def main():
    rows = []
    for sc in SCENARIOS:
        print("=" * 68)
        print(f"시나리오: {sc['name']}")
        print("=" * 68)

        # 두 방식 각각 새 executor로 (상태 공유 방지)
        rule_exec = SimExecutor(scripted=dict(sc["scripted"]))
        rule_run = await MissionRunner(rule_exec, decision_mode="rule", allowed_waypoints=SIM_WAYPOINTS).run(COMMAND)

        llm_exec = SimExecutor(scripted=dict(sc["scripted"]))
        llm_run = await MissionRunner(llm_exec, decision_mode="llm", allowed_waypoints=SIM_WAYPOINTS).run(COMMAND)

        rule_path = decisions_str(rule_run)
        llm_path = decisions_str(llm_run)
        differs = rule_path != llm_path

        print(f"  [Rule] {rule_path}")
        print(f"  [LLM ] {llm_path}")
        print(f"  판단 경로 차이: {'있음  ← LLM이 다르게 대응' if differs else '없음'}")
        print()

        rows.append({
            "scenario": sc["name"],
            "rule_success": rule_run["success"], "rule_steps": rule_run["steps"],
            "rule_decisions": rule_path,
            "llm_success": llm_run["success"], "llm_steps": llm_run["steps"],
            "llm_decisions": llm_path,
            "decisions_differ": differs,
        })

    with open("comparison_result.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("comparison_result.csv 저장 완료 →", len(rows), "개 시나리오")
    diff_count = sum(1 for r in rows if r["decisions_differ"])
    print(f"→ {len(rows)}개 중 {diff_count}개 시나리오에서 Rule과 LLM의 판단이 달랐습니다.")


if __name__ == "__main__":
    asyncio.run(main())
