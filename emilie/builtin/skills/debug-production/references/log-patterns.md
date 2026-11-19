# Reading logs

- Find the first error in time, not the most frequent; later errors are often consequences.
- Normalize messages (replace ids, numbers, UUIDs) to cluster; count clusters per minute to see the step change.
- Compare a failing request with a succeeding one end to end using the request/trace id.
- Patterns: `Connection refused/reset` dependency down; `timeout` slow dependency or exhausted pool; `OOMKilled`/`MemoryError` memory; `too many open files` fd leak; `deadlock detected` DB locking; `certificate has expired`; `429` rate limit; repeating stack trace after a deploy time = regression.
- Percentiles over averages; check the long tail. Mask tokens, emails and IPs before sharing.
