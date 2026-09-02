**English** | [中文](plan.zh.md)

# Execution 0002 plan

1. Trace MediaCrawler CLI enums and configuration mutation.
2. Inspect all platform login and creator workflows.
3. Inspect JSONL writers, media download switches and output paths.
4. Trace bili-sync-up database, scheduler, download-state and NFO generation patterns.
5. Produce requirements, capability matrix and component architecture.
6. Validate citations and create the second bilingual commit.

## Risks and assumptions

- Upstream behavior changes frequently; every assertion is scoped to the locked SHA.
- A method name or CLI enum is not proof that the workflow works; placeholder bodies are marked unsupported.
- No live platform account is used during source analysis.
