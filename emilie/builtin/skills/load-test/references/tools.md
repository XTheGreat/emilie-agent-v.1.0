# Load testing tools

Use the bundled `scripts/loadtest.py` for a single HTTP endpoint and quick checks. Use a dedicated tool for scenarios, ramps, high rates or protocols. Tell the user before installing
anything; pin versions; confirm commands against the tool's current documentation, because flags change between releases. Remember the safety rule: only systems you own or have
permission to test.

| Tool | Good for | Notes |
|---|---|---|
| `scripts/loadtest.py` (bundled) | one URL, quick capacity checks, thresholds in CI, closed and open loop | Python threads; a few thousand req/s at most; refuses non-local hosts without `--allow-remote` |
| **k6** | scripted scenarios in JavaScript, stages/ramps, thresholds, checks, tagging, cloud or local runs | single binary; `k6 run script.js`; arrival-rate executors for open model |
| **wrk / wrk2** | very high request rates for simple endpoints (C, epoll); wrk2 adds constant-rate with correct latency | `wrk -t4 -c100 -d30s --latency URL`; wrk2 `-R rate` |
| **hey / bombardier / oha** | quick HTTP benchmarks, simple CLI | `hey -z 30s -c 50 URL`; `oha -z 30s -q 100 URL` |
| **vegeta** | constant-rate attacks with latency histogram, good in pipelines | `echo "GET URL" | vegeta attack -rate=100 -duration=30s | vegeta report` |
| **Locust** | Python scenarios, user behavior classes, web UI, distributed workers | `locust -f locustfile.py --headless -u 100 -r 10 -t 5m` |
| **Gatling** | JVM, scenario DSL, detailed HTML reports | heavier setup |
| **JMeter** | GUI/XML test plans, many protocols (JDBC, JMS, FTP) | heavy; run non-GUI for load: `jmeter -n -t plan.jmx -l out.jtl` |
| **Artillery** | YAML scenarios, WebSocket and Socket.IO | Node |
| **ab (ApacheBench)** | legacy, trivial checks | closed loop only; HTTP/1.0 without keep-alive by default; avoid for serious work |
| **ghz** | gRPC | |
| **pgbench / sysbench / redis-benchmark** | database or cache directly | tests the datastore, not the app |

## k6 example (staged load with thresholds)

```js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '1m', target: 20 },   // ramp up
    { duration: '5m', target: 20 },   // hold
    { duration: '1m', target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_failed:   ['rate<0.01'],      // under 1% errors
    http_req_duration: ['p(95)<300'],      // 95% under 300 ms
  },
};

export default function () {
  const res = http.get(`${__ENV.BASE_URL}/api/items?page=${Math.ceil(Math.random() * 50)}`);
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(1);                                // think time
}
```

Run: `k6 run -e BASE_URL=http://localhost:8080 script.js`. For capacity use the `constant-arrival-rate` or `ramping-arrival-rate` executor (open model).

## Locust example

```python
from locust import HttpUser, task, between
import random

class Shopper(HttpUser):
    wait_time = between(1, 5)
    @task(7)
    def browse(self):  self.client.get(f"/items?page={random.randint(1, 50)}")
    @task(2)
    def detail(self):  self.client.get(f"/items/{random.randint(1, 5000)}")
    @task(1)
    def search(self):  self.client.get("/search", params={"q": random.choice(["pen", "book", "lamp"])})
```

## Watching the server

| Resource | Tool |
|---|---|
| CPU, memory, disk, network | `top`/`htop`, `vmstat 1`, `iostat -x 1`, `sar`, Windows Performance Monitor, cloud metrics |
| Connections and sockets | `ss -s`, `netstat`, connection pool metrics |
| Database | slow query log, `pg_stat_statements`, `SHOW PROCESSLIST`, lock waits, connection count, cache hit ratio |
| Runtime | GC logs and pauses, thread dumps, event-loop lag (Node), goroutine count (Go) |
| Application | request rate, error rate, latency histograms (metrics endpoint, APM), queue depth |
| Logs | error rate and kinds during the run |

## Environment checklist for the generator

- Run it on a separate machine in the same network region as the target (not the server itself, unless only a smoke test).
- Raise file-descriptor limits (`ulimit -n`) for high connection counts; watch ephemeral port exhaustion (many short connections).
- Use keep-alive like real clients do; include TLS if production has it.
- Check DNS: a single resolved IP may bypass a load balancer's spread.
