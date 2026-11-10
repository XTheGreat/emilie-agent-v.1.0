# Load test types

| Type | Question | Shape | Typical duration | Pass looks like |
|---|---|---|---|---|
| **Smoke** | Does it work under minimal load? Is the script right? | 1 to 2 users | 10 to 60 s | zero errors, latency sane |
| **Load (average and peak)** | Does it meet targets at expected traffic? | ramp to the expected peak, hold | 10 to 60 min | targets met, resources below about 70% |
| **Stress** | Where does it break, and how? | step up beyond peak (125%, 150%, 200% ...) | until failure | degrades gracefully, errors stay controlled, recovers |
| **Spike** | Can it survive a sudden jump (campaign, outage recovery)? | instant jump to a high rate, then back | 5 to 15 min | no collapse, quick recovery |
| **Soak (endurance)** | Does it leak or degrade over time? | steady moderate load | 4 to 24 h | memory, connections, disk, latency stay flat |
| **Breakpoint** | What is the maximum sustainable rate? | keep ramping until a threshold fails | until threshold | a number with its bottleneck |
| **Scalability** | Does adding capacity add throughput? | repeat load with 1, 2, 4 instances | per config | roughly linear until a shared bottleneck |

## Choosing the load model

- **Closed model** (N virtual users, each waits for a response before the next request): simulates a fixed population of users with think time. Throughput falls when the server slows.
- **Open model** (arrival rate, requests start on schedule regardless of responses): simulates independent users arriving (public web, APIs, queues). It exposes queueing. Use it to measure capacity.
- Most public services behave like the open model; internal tools with a fixed set of users like the closed model. If unsure, use open for capacity and closed for user experience.

## Think time and workload mix

- Real users pause: add think time (for example 1 to 10 s) in closed-model scenarios, or the load per user is unrealistically high.
- Use proportions from production analytics: for example 70% reads of the list page, 20% detail, 8% search, 2% writes.
- Vary the data: random product ids, user accounts, search terms from a realistic distribution (a few hot items and a long tail), so caches and indexes behave as in production.
- Include authentication (token reuse, login flow separately), realistic payload sizes and headers, compression, and TLS if production uses them.

## Converting business numbers to load

- Requests per second at peak = (daily active users x requests per user per day x share in the busy hour) / 3600, then times a peak-to-average factor (2 to 5 for most sites).
- Concurrent users = arrival rate x average session duration (Little's law: L = lambda x W).
- Add headroom (typically 2x the expected peak) and growth for the planning horizon.
- Mark every assumed number and ask the user to confirm.

## Ramp patterns

```
Load:       |      ________________________
            |     /                        \
            |    /                          \___
            |___/  warm-up   hold at peak    ramp down
Stress:     |                       /|
            |                 _____/ |  keep stepping until something breaks
            |           _____/       |
            |     _____/
Spike:      |          |\
            |__________| \________________
Soak:       |   ________________________________ 8 to 24 h
            |__/
```

## Exit criteria for a run (stop early when)

- Error rate above an agreed limit (for example 5%) for more than 30 s.
- Latency p95 beyond several times the target for more than a minute.
- Server resources hit hard limits (CPU pinned, memory near OOM, disk full) or alerts fire for other services.
- Any impact on a shared system or real users appears.
- The owner asks to stop.
