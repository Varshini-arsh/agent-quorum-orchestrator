"""
Coordinates redundant task execution across independently-run worker
agents and reaches a quorum decision instead of trusting any single
agent's output.

This is the same problem solved the same way in two different fields:
Byzantine fault tolerant consensus (don't trust one node's claim) and
LLM self-consistency decoding (don't trust one sample from a model) --
applied here to a network of independent agents that might be buggy,
compromised, or just an unreliable model call.
"""
from __future__ import annotations

import base64
import json
from collections import Counter
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def _verify_result(result: dict[str, Any], public_key_b64: str) -> bool:
    doc = dict(result)
    signature_b64 = doc.pop("signature", None)
    if not signature_b64:
        return False
    try:
        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        signature = base64.b64decode(signature_b64)
    except (ValueError, KeyError):
        return False
    payload = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        public_key.verify(signature, payload)
        return True
    except InvalidSignature:
        return False


def run_task(worker_urls: list[str], task_id: str, text: str, quorum_fraction: float = 0.5) -> dict[str, Any]:
    """
    Send the same task to every worker, verify every signature, then accept
    the majority answer only if it clears `quorum_fraction` of *verified*
    responses. Unsigned or forged responses are dropped before voting, so
    they cannot influence the outcome at all.
    """
    identities: dict[str, dict[str, Any]] = {}
    raw_results: list[tuple[str, dict[str, Any]]] = []

    for url in worker_urls:
        identities[url] = httpx.get(f"{url}/identity", timeout=3).json()
        resp = httpx.post(f"{url}/execute", json={"task_id": task_id, "text": text}, timeout=3)
        raw_results.append((url, resp.json()))

    verified: list[tuple[str, str]] = []  # (worker_id, result)
    for url, result in raw_results:
        expected_worker_id = identities[url]["worker_id"]
        if result.get("worker_id") != expected_worker_id:
            continue  # claims to be a different worker than who we asked -- reject
        if _verify_result(result, identities[url]["publicKey"]):
            verified.append((expected_worker_id, result["result"]))

    tally = Counter(value for _, value in verified)
    if not tally:
        return {"task_id": task_id, "accepted": None, "quorum_met": False, "reason": "no verifiable responses"}

    winner, votes = tally.most_common(1)[0]
    total = len(verified)
    quorum_met = (votes / total) > quorum_fraction

    return {
        "task_id": task_id,
        "votes": dict(tally),
        "total_verified_responses": total,
        "accepted": winner if quorum_met else None,
        "quorum_met": quorum_met,
        "dissenting_workers": [wid for wid, value in verified if value != winner],
    }
