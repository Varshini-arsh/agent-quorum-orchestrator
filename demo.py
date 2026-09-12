"""
Boots independent worker processes (some honest, some deliberately faulty)
and runs two scenarios through the coordinator:

A) Honest majority (4 honest, 1 faulty) -- quorum is reached, and the
   faulty worker is identified by name, because every result is signed
   and therefore attributable.
B) Adversarial majority (1 honest, 2 faulty) -- quorum FAILS. This is
   shown deliberately, not hidden: any majority-vote consensus scheme is
   only as safe as its honest-majority assumption. A real deployment
   needs a reputation system to keep known-faulty agents out of the
   worker pool before they can reach a majority in the first place.

Run: python demo.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import httpx

from coordinator import run_task

TEXT = "This agent network is reliable, helpful, and genuinely great to work with."


def wait_until_up(url: str, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return True
        except httpx.TransportError:
            pass
        time.sleep(0.3)
    return False


def boot_workers(specs: list[dict]) -> list[subprocess.Popen]:
    procs = []
    for spec in specs:
        env = {**os.environ, "WORKER_ID": spec["id"], "FAULTY": str(spec["faulty"])}
        procs.append(
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "worker:app", "--port", str(spec["port"]), "--log-level", "warning"],
                env=env,
            )
        )
    for spec in specs:
        if not wait_until_up(f"http://127.0.0.1:{spec['port']}/identity"):
            raise RuntimeError(f"{spec['id']} did not start in time")
    return procs


def run_scenario(name: str, specs: list[dict], expected_accepted: str) -> None:
    print(f"\n=== Scenario: {name} ===")
    print("workers:", [(s["id"], "FAULTY" if s["faulty"] else "honest") for s in specs])
    procs = boot_workers(specs)
    try:
        urls = [f"http://127.0.0.1:{s['port']}" for s in specs]
        result = run_task(urls, task_id=name, text=TEXT)
        print("result:", result)
        assert result["quorum_met"] is True, f"expected quorum to be met in {name}"
        assert result["accepted"] == expected_accepted, (
            f"expected '{expected_accepted}' in {name}, got '{result['accepted']}'"
        )
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


def main() -> None:
    run_scenario(
        "honest-majority",
        [
            {"id": "w1", "port": 9301, "faulty": False},
            {"id": "w2", "port": 9302, "faulty": False},
            {"id": "w3", "port": 9303, "faulty": False},
            {"id": "w4", "port": 9304, "faulty": False},
            {"id": "w5-faulty", "port": 9305, "faulty": True},
        ],
        expected_accepted="positive",
    )
    run_scenario(
        "adversarial-majority",
        [
            {"id": "w1", "port": 9311, "faulty": False},
            {"id": "w2-faulty", "port": 9312, "faulty": True},
            {"id": "w3-faulty", "port": 9313, "faulty": True},
        ],
        # The two faulty workers deterministically flip to the SAME wrong
        # answer, so quorum confidently accepts it -- the whole point of
        # this scenario. Asserting the exact wrong answer here (not just
        # "quorum_met") is what would actually catch a regression in the
        # flip logic or the vote tally.
        expected_accepted="negative",
    )
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
