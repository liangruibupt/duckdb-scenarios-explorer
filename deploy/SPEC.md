# Deploy spec — chat-BI agent on AgentCore (scenarios 04 + 07)

AI-DLC: this is the *inspect/spec* step for deploying a REAL Bedrock AgentCore
Runtime that embodies both scenario 04 (NL → DuckDB SQL over S3 Parquet) and
scenario 07 (DuckDB embedded per-agent, shared hive-partitioned Parquet on S3).

## What we deploy
One AgentCore Runtime, **`duckdb_chatbi`**, whose container:
- embeds DuckDB (in-process, no server) — the scenario 07 pattern,
- reads shared hive-partitioned Parquet at
  `s3://cdh-ingest-demo/duckdb-demo/nyc_taxi/**/*.parquet` via `httpfs` +
  `credential_chain`,
- turns a natural-language `prompt` into DuckDB SQL (scenario 04's `rule_plan`,
  with a Bedrock-Converse LLM planner when `USE_LLM=1`),
- returns `{sql, rows}` (or an error/help message).

## Contract
- Entrypoint: `BedrockAgentCoreApp`, `@app.entrypoint` handler.
- Input:  `{"prompt": "busiest 5 zones"}`
- Output: `{"sql": "<SELECT ...>", "rows": [...], "engine": "rule|llm"}`
- Unsupported prompt → `{"error": "...", "hint": "<supported shapes>"}`.

## Infra (us-east-1, account 747411437379)
- `agent/app.py` entrypoint + `agent/requirements.txt` (duckdb, boto3,
  bedrock-agentcore).
- `agentcore configure` → generates `.bedrock_agentcore.yaml` + Dockerfile.
- `agentcore launch` → CodeBuild builds ARM64 image → ECR → CreateAgentRuntime.
- Exec role needs: `s3:GetObject`/`s3:ListBucket` on `cdh-ingest-demo`,
  `bedrock:InvokeModel` (LLM planner). Runtime SLRs (network + runtime-identity).

## Guardrail / hand-off boundary
IAM writes (exec-role policy, service-linked roles) are hard-blocked for the
agent by Kiro Crew. One-shot fix: attach **`BedrockAgentCoreFullAccess`** to
`OpenClawInstanceRole`, or run the specific `iam` commands provided. Everything
up to the IAM step is built by the agent; the IAM step and any guardrail-blocked
`launch` sub-step are handed to Liang with exact commands.

## Test (acceptance)
- `agentcore invoke '{"prompt":"How many trips were there?"}'` → a positive count.
- `agentcore invoke '{"prompt":"busiest 5 zones"}'` → 5 rows.
- `agentcore invoke '{"prompt":"average tip by hour"}'` → 24 rows.
- Verifies live: embedded DuckDB in the Runtime reads S3 Parquet in place and
  answers NL questions — scenarios 04 + 07 proven in the cloud.
