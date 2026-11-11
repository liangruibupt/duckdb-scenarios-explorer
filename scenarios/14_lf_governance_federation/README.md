# 14 — Lake Formation governance + lake / non-lake join · Lake Formation 治理 + 湖内外数据 join

> **English and 中文.** Each section gives the English text first, then the
> Chinese text. 每一节先英文，后中文。

This scenario fills the two gaps the
[AgentCore DuckDB data agent article](https://aws.amazon.com/cn/blogs/china/amazon-bedrock-agentcore-build-governance-duckdb-data-agent/)
describes and the rest of this repo did not cover:

1. **Lake Formation as the policy authority (L4).** Lake Formation grants are
   compiled into the same RLS/CLS policies that scenario 08's `govern()` already
   enforces, so changing a grant in Lake Formation changes what the agent's next
   SQL may return. Enforcement still happens before the engine.
2. **Joining lake data with a non-lake source (L5).** A non-lake system is
   reached through a *registered tool* (the article uses AgentCore Gateway), its
   rows land in the session as an owner-bound handle, and the agent joins that
   handle with governed lake tables in one DuckDB session.

本场景补上 [AgentCore DuckDB Data Agent 文章](https://aws.amazon.com/cn/blogs/china/amazon-bedrock-agentcore-build-governance-duckdb-data-agent/)
中描述、而本仓库之前没有覆盖的两块：

1. **以 Lake Formation 作为权限来源（L4）。** 把 Lake Formation 的授权编译成场景 08 的 `govern()` 已经在执行的
   行列级策略。在 Lake Formation 里改了授权，agent 下一条 SQL 能返回的数据就跟着变。执行点仍然在引擎之前。
2. **湖上数据 join 非湖数据源（L5）。** 通过一个*注册过的工具*访问非湖系统（文章里用的是 AgentCore Gateway），
   结果作为绑定属主的句柄落进会话，agent 再在同一个 DuckDB 会话里把这个句柄和受治理的湖表 join 起来。

## Files · 文件

| File | Role |
|---|---|
| `lf_policy.py` | Lake Formation snapshot → scenario 08 `Policy` per `tenant:role` |
| `fetch_lf.py` | Builds that snapshot from a live account with read-only APIs (`ListPermissions`, `ListDataCellsFilter`, `glue:GetTables`) |
| `federation.py` | `FederatedSession`: registered tools into a non-lake source, `_x_<n>` handles, governed queries over lake tables + handles |
| `demo.py` | End-to-end run: offline (DuckLake lake + SQLite CRM) by default, or a real S3 Tables bucket with `--s3tables-arn` |
| `fixtures/lf_snapshot.json` | Offline Lake Formation account (placeholder account ID) |

| 文件 | 作用 |
|---|---|
| `lf_policy.py` | Lake Formation 快照 → 每个 `tenant:role` 的场景 08 `Policy` |
| `fetch_lf.py` | 用只读 API（`ListPermissions`、`ListDataCellsFilter`、`glue:GetTables`）从真实账号生成快照 |
| `federation.py` | `FederatedSession`：调用非湖数据源的注册工具、`_x_<n>` 句柄、对湖表和句柄执行受治理的查询 |
| `demo.py` | 端到端演示：默认离线（DuckLake 作湖、SQLite 作 CRM），或用 `--s3tables-arn` 接真实的 S3 Tables |
| `fixtures/lf_snapshot.json` | 离线的 Lake Formation 账号（账号 ID 为占位符） |

## How Lake Formation grants map · Lake Formation 授权如何映射

| Lake Formation grant | Becomes |
|---|---|
| `SELECT` on `Table` | All rows, all columns |
| `SELECT` on `Table` with `TableWildcard` | All tables in the database, all rows and columns |
| `SELECT` on `TableWithColumns` (`ColumnNames`) | Those columns allowed; the rest denied |
| `SELECT` on `TableWithColumns` (`ColumnWildcard` + `ExcludedColumnNames`) | Excluded columns denied |
| `SELECT` on a `DataCellsFilter` | `RowFilter.FilterExpression` as the row filter (`AllRowsWildcard` = all rows) plus the filter's column scope |
| Several grants on one table | Union, as Lake Formation does: columns unioned, row filters ORed |
| `DESCRIBE` only, other resource types, unmapped principal ARN | Nothing (deny-all) |
| Unparseable filter, grant on a filter or table not in the snapshot | Table dropped from the policy (fail-closed), never granted unfiltered |

Principal ARNs map to the agent's `tenant:role` through a `principal_map` you
provide; in the AWS sample this identity comes from AgentCore Identity's
inbound JWT.

| Lake Formation 授权 | 映射为 |
|---|---|
| 对 `Table` 的 `SELECT` | 所有行、所有列 |
| 对 `Table` 加 `TableWildcard` 的 `SELECT` | 数据库里所有表的所有行和列 |
| 对 `TableWithColumns`（`ColumnNames`）的 `SELECT` | 只允许这些列，其余列禁止 |
| 对 `TableWithColumns`（`ColumnWildcard` + `ExcludedColumnNames`）的 `SELECT` | 被排除的列禁止 |
| 对 `DataCellsFilter` 的 `SELECT` | `RowFilter.FilterExpression` 作为行过滤（`AllRowsWildcard` 表示所有行），加上过滤器自己的列范围 |
| 同一张表的多条授权 | 按 Lake Formation 的规则取并集：列取并集，行过滤用 OR 连接 |
| 只有 `DESCRIBE`、其他资源类型、没映射的主体 ARN | 什么都不给（全部拒绝） |
| 解析不了的过滤条件、授权指向快照里没有的过滤器或表 | 从策略里去掉这张表（失败即拒绝），绝不会不加过滤地放行 |

主体 ARN 通过你提供的 `principal_map` 映射到 agent 的 `tenant:role`；在 AWS 样例里，这个身份来自 AgentCore Identity
的入站 JWT。

## How the join is governed · join 如何受治理

1. The model calls a registered tool by name (`crm_accounts`), never free SQL
   against the external system. Only principals on the tool's allow-list may call
   it, and only declared parameters are accepted.
2. The tenant is bound from the session principal, so the model cannot ask for
   another tenant's rows (passing `tenant=` is refused).
3. The result lands as a temp table `_x_<n>` owned by the session.
4. A query may reference only handles this session minted; then the whole
   statement, lake tables included, goes through `govern()` and the cost gate.

1. 模型按名字调用注册过的工具（`crm_accounts`），不能对外部系统写任意 SQL。只有在工具允许列表里的主体能调用，
   而且只接受声明过的参数。
2. 租户取自会话主体，模型没法要其他租户的数据（传 `tenant=` 会被拒绝）。
3. 结果落成会话自己拥有的临时表 `_x_<n>`。
4. 查询只能引用本会话生成的句柄；然后整条语句（包括湖表）都要经过 `govern()` 和成本闸门。

## Run · 运行

```bash
pip install -r requirements.txt
python scenarios/14_lf_governance_federation/demo.py            # offline

# Your account (read-only): snapshot your grants, then query a real S3 Tables bucket
python scenarios/14_lf_governance_federation/fetch_lf.py \
  --database <db> --principal-map map.json --out lf_snapshot.json
python scenarios/14_lf_governance_federation/demo.py \
  --snapshot lf_snapshot.json --s3tables-arn arn:aws:s3tables:<region>:<acct>:bucket/<name>
```

Offline output (abridged):

```
== Policies compiled from Lake Formation ==
  acme:analyst    orders   rows: (tenant = 'acme'); denied columns: card_number
  acme:analyst    refunds  rows: all; denied columns: reason
  acme:auditor    orders   rows: all; denied columns: none
  globex:analyst  orders   rows: (tenant = 'globex'); denied columns: card_number

== acme:analyst: call CRM tool, then join with the lake ==
  governed: SELECT a.account_name, ... FROM orders AS o JOIN _x_1 AS a
            ON o.account_id = a.account_id WHERE (tenant = 'acme') GROUP BY ALL ...
    ('Acme Wholesale', 'enterprise', 1000, 97492.5)
    ('Acme Online', 'smb', 1000, 57494.0)

== Refusals (all before the engine) ==
  acme:analyst names a denied column: refused -> column 'card_number' denied for this role
  acme:analyst reads globex's handle: refused -> handle(s) ['_x_2'] not owned by this session
  acme:viewer has DESCRIBE only: refused -> table 'orders' not permitted for this role
  model tries to pass tenant='globex': refused -> tool 'crm_accounts' does not accept ['tenant']
```

`fetch_lf.py` was run read-only against a real account to check the API calls.
That account does not use Lake Formation permissions, so it returned no grants,
and the mapping rules above are tested against the documented API shapes in the
fixture. The `--s3tables-arn` path has not been run against a live S3 Tables
bucket.

`fetch_lf.py` 已经在一个真实账号上只读运行过，用来验证 API 调用。那个账号没有使用 Lake Formation 权限，所以没有返回
任何授权，上面的映射规则是用夹具里按官方文档构造的 API 结构测试的。`--s3tables-arn` 这条路径还没有在真实的 S3 Tables
存储桶上跑过。

## Limits · 限制

- Policies are compiled from a snapshot. A grant changed in Lake Formation takes
  effect when the snapshot is refreshed (per session start in the AWS sample).
- Tables are matched by bare name, as in scenario 08, so two databases with the
  same table name in one session would collide.
- LF-Tag based grants (LF-TBAC) are not expanded; they grant nothing here.
- Lake Formation row-filter expressions are PartiQL; simple predicates parse as
  DuckDB SQL, and anything that does not parse drops the table.

- 策略是从快照编译的。Lake Formation 里改的授权，要等快照刷新后才生效（AWS 样例里是每次会话开始时刷新）。
- 和场景 08 一样按不带库名的表名匹配，同一会话里两个库有同名表会冲突。
- 不展开基于 LF-Tag 的授权（LF-TBAC），这类授权在这里什么都不给。
- Lake Formation 的行过滤表达式是 PartiQL；简单的谓词能按 DuckDB SQL 解析，解析不了的会让这张表被拒绝。
