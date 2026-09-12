"""
An independent worker agent that executes a task and signs its own result.
Signing the result -- not just the worker's identity -- means a coordinator
can prove exactly which worker produced which answer; no worker can deny
an answer it gave, and nobody can forge a result on another worker's
behalf.

A worker can be started in FAULTY mode to simulate a buggy or adversarial
agent that deliberately returns a wrong answer. That's not an edge case
being avoided -- it's the whole point: coordinator.py exists to catch it.

Config: WORKER_ID, WORKER_PORT, FAULTY=true|false
Run standalone: WORKER_ID=w1 FAULTY=false uvicorn worker:app --port 9301
"""
from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from pydantic import BaseModel

WORKER_ID = os.environ.get("WORKER_ID", "worker")
FAULTY = os.environ.get("FAULTY", "false").lower() == "true"

_private_key = Ed25519PrivateKey.generate()
_public_key_b64 = base64.b64encode(_private_key.public_key().public_bytes_raw()).decode("ascii")

app = FastAPI(title=f"Worker[{WORKER_ID}]")

# A deliberately simple, deterministic "task" so correctness is checkable
# by majority vote: classify sentiment by keyword count. Swap for a real
# LLM call and the exact same quorum logic still applies -- that's the
# point, since LLM outputs are exactly the kind of non-deterministic,
# occasionally-wrong result you shouldn't trust from a single sample.
POSITIVE_WORDS = {"good", "great", "excellent", "love", "amazing", "helpful", "reliable", "trust"}
NEGATIVE_WORDS = {"bad", "terrible", "hate", "broken", "fail", "unreliable", "worst", "scam"}


def _classify(text: str) -> str:
    words = [w.strip(".,!?") for w in text.lower().split()]
    pos = sum(1 for w in words if w in POSITIVE_WORDS)
    neg = sum(1 for w in words if w in NEGATIVE_WORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


_FLIP = {"positive": "negative", "negative": "positive", "neutral": "negative"}


class ExecuteRequest(BaseModel):
    task_id: str
    text: str


@app.get("/identity")
def identity() -> dict:
    return {"worker_id": WORKER_ID, "publicKey": _public_key_b64, "faulty_mode": FAULTY}


@app.post("/execute")
def execute(req: ExecuteRequest) -> dict:
    honest_result = _classify(req.text)
    result = _FLIP[honest_result] if FAULTY else honest_result

    unsigned = {"task_id": req.task_id, "worker_id": WORKER_ID, "result": result}
    payload = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = _private_key.sign(payload)
    return {**unsigned, "signature": base64.b64encode(signature).decode("ascii")}
