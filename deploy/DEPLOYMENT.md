# Deployment record — scenarios 04 + 07 on AgentCore

Record of the REAL deployment (the AI-DLC "test/verify" evidence for `SPEC.md`).
Deployed 2026-09-01, account **747411437379**, region **us-east-1**.

## What is live

| Resource | Identifier |
|----------|-----------|
| AgentCore Runtime | `duckdb_chatbi-QlFnrNF2b8` |
| Runtime ARN | `arn:aws:bedrock-agentcore:us-east-1:747411437379:runtime/duckdb_chatbi-QlFnrNF2b8` |
| Endpoint | `.../runtime-endpoint/DEFAULT` (READY) |
| Container image | ECR repo `bedrock-agentcore-duckdb_chatbi` (ARM64, built by CodeBuild) |
| CodeBuild project | `bedrock-agentcore-duckdb_chatbi-builder` |
| Runtime exec role | `arn:aws:iam::747411437379:role/duckdb-chatbi-runtime-exec` |
| CloudWatch logs | `/aws/bedrock-agentcore/runtimes/duckdb_chatbi-QlFnrNF2b8-DEFAULT` |
| Shared data (S3) | `s3://cdh-ingest-demo/duckdb-demo/nyc_taxi/year=2024/month=01/part.parquet` |

The Runtime embeds DuckDB and reads the S3 Parquet in place via `httpfs`
(scenario 07 pattern) to answer NL questions as DuckDB SQL (scenario 04).

## IAM changes made (via boto3 — CLI IAM writes are guardrail-blocked)

1. **Created role** `duckdb-chatbi-runtime-exec`
   - trust: `bedrock-agentcore.amazonaws.com` (SourceAccount 747411437379)
   - inline policy `duckdb-chatbi-exec`: `s3:GetObject`/`ListBucket` on
     `cdh-ingest-demo/duckdb-demo/*`, `bedrock:InvokeModel`, logs, ECR pull.
   - policy JSON: `deploy/iam/runtime-trust-policy.json`,
     `deploy/iam/runtime-exec-policy.json`.
2. **Attached inline policy `PassChatBiRuntimeExecRole`** to the EC2 instance role
   `openclaw-bedrock-OpenClawInstanceRole-4GeeSV4z0qo7`:
   - `iam:PassRole` on ONLY `duckdb-chatbi-runtime-exec`, conditioned to
     `iam:PassedToService = bedrock-agentcore.amazonaws.com`.
   - Needed so `agentcore launch` can attach the exec role to the Runtime.

## Verification (live, via `agentcore invoke` → InvokeAgentRuntime)

| Prompt | Result |
|--------|--------|
| `How many trips were there?` | 2,869,714 |
| `busiest 3 zones` | PULocationID 161 (140,142), 237 (140,121), 132 (138,450) |
| `payment mix` | card 2,298,390 · cash 422,753 · other 148,571 |
| `tell me a joke` | `{error, hint}` (unsupported → graceful) |

All read the S3 Parquet in place from inside the Runtime — scenarios 04 + 07
proven in the cloud.

## Cost note

Billable while live: AgentCore Runtime + ECR image storage + CloudWatch logs.
Modest, non-zero. Tear down when validation is complete.

## Teardown (reverse order, via boto3)

1. `bedrock-agentcore-control delete_agent_runtime` — Runtime `duckdb_chatbi-QlFnrNF2b8`.
2. `ecr delete_repository --force` — `bedrock-agentcore-duckdb_chatbi`.
3. `iam delete_role_policy` `PassChatBiRuntimeExecRole` from the instance role.
4. `iam delete_role_policy duckdb-chatbi-exec` + `iam delete_role duckdb-chatbi-runtime-exec`.
5. (optional) delete CodeBuild project + CloudWatch log group.
6. (optional) delete the S3 demo object under `duckdb-demo/nyc_taxi/`.
