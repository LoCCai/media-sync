**English** | [中文](progress.zh.md)

# Progress

Planning baseline; implementation has not started. Read current service/policy/projection and previous canary records. Current heartbeat failure cancels its handler and falls back to schema_invalid; Job projection deliberately omits its already stored last_error_code. Prior injected experiments reproduce but do not uniquely explain production's terminal Job + running Run. Fix diagnostic visibility without claiming a production lock root cause.

Full product goal and Cookie entry remain incomplete. No current production process is being waited on; the last canary is terminal.

