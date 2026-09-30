# Deployment record — scenario 08 governed data agent

Deployed 2026-09-28, account **<ACCOUNT_ID>**, us-east-1.

## Live resources

| Resource | Identifier |
|----------|-----------|
| Runtime | `duckdb_governed-jUL2s6GPOv` |
| Runtime ARN | `arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:runtime/duckdb_governed-jUL2s6GPOv` |
| Exec role | `arn:aws:iam::<ACCOUNT_ID>:role/duckdb-governed-runtime-exec` (S3 read + Bedrock + logs + ECR) |
| ECR image | `bedrock-agentcore-duckdb_governed` (ARM64, CodeBuild) |
| Data | `s3://cdh-ingest-demo/duckdb-demo/nyc_taxi/**/*.parquet` |

The container embeds DuckDB + sqlglot and runs every statement through the
scenario-08 **govern → cost → execute → shape** pipeline under the caller's
identity, reading S3 in place via httpfs.

## Verified

- **Local (with `--as`)**, live against S3: analyst → RLS `payment_type=1`
  applied (2,319,046 of 2.87M trips); junior → CLS refusal on `tip_amount`;
  anonymous → deny-all.
- **Cloud, per-persona over the wire** (Cognito JWT → authorizer → claims):
  - `analyst-a` → `acme:analyst`, RLS applied, **2,319,046** trips
  - `junior-a` → `acme:junior`, **CLS refusal** on `tip_amount` at govern
  - `admin-a` → `acme:admin`, passthrough, **2,964,624** trips
  Same governed pipeline, three policy-correct outcomes, identity from a
  validated JWT — not a UI toggle.

## Identity (JWT authorizer — now live)

| Resource | Identifier |
|----------|-----------|
| Cognito user pool | `us-east-1_Z0mDSj06D` |
| App client | `1h2m2mob3lomip7v8hqmrnv692` (secret; USER_PASSWORD_AUTH) |
| Discovery URL | `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Z0mDSj06D/.well-known/openid-configuration` |
| Personas | `admin-a` (acme:admin), `analyst-a` (acme:analyst), `junior-a` (acme:junior) |

The runtime is configured with `customJWTAuthorizer` (discoveryUrl +
allowedAudience = the app client id) and `--request-header-allowlist
Authorization`. `custom:tenant`/`custom:role` ride on the **ID token**; the
entrypoint decodes the authorizer-validated JWT to read them. Invoke over HTTPS
with `Authorization: Bearer <IdToken>` (SigV4/IAM invoke is now refused —
"authorization method mismatch"). Reproduce with `deploy/persona_invoke.py`.

## Cost

Billable while live: AgentCore Runtime + ECR + CloudWatch logs. Modest.

## Teardown (boto3, reverse order)

1. `bedrock-agentcore-control delete_agent_runtime` — `duckdb_governed-jUL2s6GPOv`
2. `ecr delete_repository --force bedrock-agentcore-duckdb_governed`
3. `iam delete_role_policy PassGovernedExec` from the instance role
4. `iam delete_role_policy duckdb-governed-exec` + `delete_role duckdb-governed-runtime-exec`
5. CodeBuild project + log group
6. `cognito-idp delete-user-pool --user-pool-id us-east-1_Z0mDSj06D` (removes the
   pool, app client and persona users in one call)
