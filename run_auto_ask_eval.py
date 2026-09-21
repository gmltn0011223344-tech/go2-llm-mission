"""
run_auto_ask_eval.py  (프로젝트 루트에서 실행) — AUTO/ASK 판단 평가

    python3 run_auto_ask_eval.py          # LLM 판단 (API 키 없으면 mock)
    python3 run_auto_ask_eval.py --rule   # Rule 대체 정책만

1) 판단 평가: 정답표(agent/evaluation.py) 8개 상황에서 AUTO/ASK/정지 선택을 채점
2) 임무 평가: 시뮬레이터로 임무 전체를 실행해 종료 상태 확인 (ASK는 사용자 답변 없이 멈춤)
결과: auto_ask_result.csv

주의: API 키 없이 실행한 결과(mock)는 정답표·채점 코드 점검용이며 LLM 성능이 아닙니다.
"""

import asyncio
import csv
import sys

from agent.evaluation import GOLD_SCENARIOS, outcome, score
from agent.mission_runner import MissionRunner
from agent.sim_executor import SimExecutor

COMMAND = "A 지점으로 가서 병이 있는지 확인하고 돌아와"

MISSIONS = [
    ("정상", {}, True),
    ("경로실패 1회", {"A": "NO_PATH"}, True),
    ("경로실패 반복", {"A": "NO_PATH"}, False),
    ("미발견 1회", {"BOTTLE": "TARGET_NOT_FOUND"}, True),
    ("미발견 반복", {"BOTTLE": "TARGET_NOT_FOUND"}, False),
    ("오류", {"A": "ERROR"}, False),
]


async def main():
    mode = "rule" if "--rule" in sys.argv else "llm"
    runner = MissionRunner(executor=None, decision_mode=mode)

    rows, pairs = [], []
    print(f"[1] 판단 평가 ({mode})")
    for sc in GOLD_SCENARIOS:
        d = runner.decide(sc["state"], sc["ctx"])
        pred = outcome(d)
        pairs.append((sc["expected"], pred))
        mark = "O" if pred == sc["expected"] else "X"
        print(f"  {mark} {sc['name']:<12} 정답={sc['expected']:<4} 판단={pred:<4} ({d['source']}) {d['reason']}")
        rows.append({"type": "decision", "name": sc["name"], "expected": sc["expected"],
                     "result": pred, "source": d["source"], "detail": d["question"] or d["reason"]})
    s = score(pairs)
    print(f"  → {s['total']}개 중 {s['correct']}개 일치 | ASK 기준 Precision {s['ask_precision']:.2f} "
          f"Recall {s['ask_recall']:.2f} F1 {s['ask_f1']:.2f}\n")

    print(f"[2] 임무 평가 ({mode}) — 명령: {COMMAND}")
    for name, scripted, recover in MISSIONS:
        r = await MissionRunner(SimExecutor(scripted=dict(scripted), recover_on_retry=recover),
                                decision_mode=mode).run(COMMAND)
        path = " | ".join(f"{e['state']}→[{e['mode']}]{e['next_action'] or 'ASK'}" for e in r["log"])
        print(f"  {name:<10} {r['status']:<17} {path}")
        rows.append({"type": "mission", "name": name, "expected": "", "result": r["status"],
                     "source": "", "detail": path})

    with open("auto_ask_result.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("\nauto_ask_result.csv 저장 완료")


if __name__ == "__main__":
    asyncio.run(main())
