# NANDA Quorum Orchestrator

A working demonstration of the fourth infrastructure gap Project NANDA
(MIT Media Lab) names for the "Internet of AI Agents" — **Orchestration**
— alongside a real, unavoidable problem in any multi-agent network:
you cannot fully trust the output of any single agent, whether it's
buggy, compromised, or just an unreliable LLM call.

Companion to [`agentfacts-mini-registry`](https://github.com/Varshini-arsh/agentfacts-mini-registry),
which covers Discovery, Identity/CA, and Attestation. Together the two
projects touch all four choke points NANDA names.

## The idea

Don't trust one agent's answer — get the same task done independently by
several agents and only accept the answer if enough of them agree. This
is exactly how two different fields solve the same problem: **Byzantine
fault tolerant consensus** (don't trust one node's claim) and **LLM
self-consistency decoding** (don't trust one sample from a model). Here
it's applied to a small network of independent agent processes.

## What it does

- `worker.py` — an independent agent that executes a toy but genuinely
  checkable task (sentiment classification by keyword count) and **signs
  its own result** with its own Ed25519 key. Signing the *output*, not
  just the agent's identity, means every answer is attributable — nobody
  can forge a result on another worker's behalf, and no worker can later
  deny an answer it gave.
- `coordinator.py` — sends the same task to every worker, verifies every
  signature, drops anything unsigned or forged, then accepts the
  majority answer only if it clears a quorum threshold.
- A worker can run in `FAULTY` mode to simulate a buggy or adversarial
  agent that deliberately flips its answer — not an edge case being
  avoided, but the entire reason the quorum mechanism exists.

## Run it

```bash
pip install -r requirements.txt
python demo.py
```

Two scenarios, both booting real independent processes:

**Scenario A — honest majority (4 honest, 1 faulty):**
```
{'accepted': 'positive', 'quorum_met': True, 'dissenting_workers': ['w5-faulty']}
```
Quorum correctly reaches the true answer, and the faulty worker is
identified by name — because its result was signed, it can't hide.

**Scenario B — adversarial majority (1 honest, 2 faulty):**
```
{'accepted': 'negative', 'quorum_met': True, 'dissenting_workers': ['w1']}
```
This is the important result, and it's shown honestly rather than
hidden: the two faulty workers agree with each other on the *same wrong*
answer, so quorum doesn't just fail to decide — it **confidently accepts
the wrong answer**. Signatures only prove who said what; they say
nothing about whether a majority of who-said-what is trustworthy.

## Why this matters (and where it stops)

Signed, quorum-verified execution solves attribution and tamper-evidence,
but it inherits the classic limit of every majority-vote consensus
scheme: it only works under an honest-majority assumption. Once faulty or
colluding agents control the majority of a task's worker pool, the system
fails *confidently*, not safely. That's precisely why this needs to be
paired with a reputation layer that keeps known-faulty agents from
accumulating majority share in the first place — see
`agentfacts-mini-registry`'s federated, tamper-evident reputation ledger
for a first attempt at exactly that.

## What I'd build next

- Weight votes by each worker's reputation score (from the companion
  project) instead of one-agent-one-vote, so a single trusted agent can
  outweigh several low-reputation ones.
- Replace the toy sentiment task with a real LLM call per worker, so the
  same quorum logic is guarding against genuine model non-determinism,
  not just simulated faults.
- Let the coordinator itself be one of several redundant coordinators,
  so no single coordinator is a trusted bottleneck either.
