# Deployment record — scenario 08 governed data agent

Deployed 2026-09-28, account **747411437379**, us-east-1.

## Live resources

| Resource | Identifier |
|----------|-----------|
| Runtime | `duckdb_governed-jUL2s6GPOv` |
| Runtime ARN | `arn:aws:bedrock-agentcore:us-east-1:747411437379:runtime/duckdb_governed-jUL2s6GPOv` |
| Exec role | `arn:aws:iam::747411437379:role/duckdb-governed-runtime-exec` (S3 read + Bedrock + logs + ECR) |
| ECR image | `bedrock-agentcore-duckdb_governed` (ARM64, CodeBuild) |
| Data | `s3://cdh-ingest-demo/duckdb-demo/nyc_taxi/**/*.parquet` |

The container embeds DuckDB + sqlglot and runs every statement through the
scenario-08 **govern → cost → execute → shape** pipeline under the caller's
identity, reading S3 in place via httpfs.

## Verified

- **Local (with `--as`)**, live against S3: analyst → RLS `payment_type=1`
  applied (2,319,046 of 2.87M trips); junior → CLS refusal on `tip_amount`;
  anonymous → deny-all.
- **Cloud (`agentcore invoke`)**: with no JWT claims the principal is `anonymous`
  and `trips` is refused at `govern` — **fail-closed in the cloud, verified**.

## Known gap — JWT identity (the scheduling layer)

This deploy uses AgentCore **IAM auth**, so there is no per-user JWT on the wire;
every cloud invoke is `anonymous` → deny-all. To exercise a real persona over the
wire, the runtime needs a **Cognito pool + `customJWTAuthorizer`** (discoveryUrl +
allowedAudience) and `--request-header-allowlist Authorization`, with
`custom:tenant`/`custom:role` on the ID token. That Cognito stack is the next
piece (see aws-samples for the CDK shape). The governance/pipeline code already
reads claims from the request context — only the authorizer + pool are missing.

## Cost

Billable while live: AgentCore Runtime + ECR + CloudWatch logs. Modest.

## Teardown (boto3, reverse order)

1. `bedrock-agentcore-control delete_agent_runtime` — `duckdb_governed-jUL2s6GPOv`
2. `ecr delete_repository --force bedrock-agentcore-duckdb_governed`
3. `iam delete_role_policy PassGovernedExec` from the instance role
4. `iam delete_role_policy duckdb-governed-exec` + `delete_role duckdb-governed-runtime-exec`
5. CodeBuild project + log group
