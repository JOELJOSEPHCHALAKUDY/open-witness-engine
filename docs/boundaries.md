# Safety boundaries and rationale

Open Witness Engine is deliberately confined to an observation-and-memory role.
This document explains why each boundary exists and what it protects against. The
boundaries are architectural invariants, not preferences.

## 1. Never in a safety or control path

On-robot control is hard real-time: control loops run at 100 Hz–1 kHz with bounded
jitter, and any function that can influence motion falls under a functional-safety
regime (ISO 26262 with ASIL ratings, ISO 21448/SOTIF, UL 4600 for autonomy, ISO
10218 / 3691-4 for industrial and AGV robots). OWE is an asynchronous, Python,
LLM-adjacent memory service with no timing guarantees and no safety certification.
Placing it anywhere a deadline miss or a wrong decision could move a robot is
categorically unsafe. This is structural, not tunable.

## 2. Advisory only — never defines the safe action set

OWE may estimate operator *preferences* (prefer less congested routes, escalate
after two failed recoveries, notify before retrying a blocked manipulation). It may
propose a recovery action. It must never define which actions are *allowed*. The
safe formulation keeps OWE strictly inside a preference term:

```
A_safe = { a in A | C_safety(state, a) = true }        # owned by the safety system
a*     = argmin over a in A_safe ( J_task(a) + λ · J_operator_preference(a) )
                                                        # OWE contributes only J_operator_preference
```

A trusted, deterministic gateway — independent of OWE, retrieval, and any LLM — must
compute `A_safe` and mediate execution. Learned preferences may influence ranking
only after context matching, confidence checks, contradiction detection, and human
review.

## 3. Non-blocking and fail-open

Capture must use a bounded queue and drop or spool rather than block a robot process.
The robot must operate normally when OWE is slow, degraded, or unreachable. OWE is a
rebuildable, non-authoritative analytics/memory layer — never a system of record on
the critical path.

## 4. Complements the flight recorder; stores no raw sensor data

`rosbag2` (MCAP) and `ros2_tracing` already provide low-overhead, timing-accurate raw
and flight-recorder capture. A single robot emits orders of magnitude more data than
a decision-memory layer should hold (high-rate IMU/odometry, camera and LiDAR streams
at MB/s–GB/s). OWE stores compact decision records, causal links, content hashes, and
*references* into those recordings — never the raw streams themselves.

## Not a certified logger

Regulated event logging for automated driving (EDR under UN R160, DSSAD under UN R157)
demands tamper-evident, fixed-schema, certified storage. OWE is not that and does not
claim to be. If a hash-chained, tamper-evident audit trail is later required, it is an
added, separately-assured component — not a reason to trust OWE as a system of record.
