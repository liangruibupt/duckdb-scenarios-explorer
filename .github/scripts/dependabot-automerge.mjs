// Dependabot PR 在 CI 通过后能不能自动合并：只放行单个依赖的兼容升级，其余留给人看。
// 用法：node dependabot-automerge.mjs <pr.json> <CI 测过的 head SHA> <默认分支>
// pr.json 是 gh pr view --json state,author,baseRefName,headRefName,headRefOid,title,commits 的输出。
// 输出一行 "merge: 原因" 或 "skip: 原因"。
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const PR_AUTHOR = 'app/dependabot';
const COMMIT_AUTHOR = 'dependabot[bot]';
// "build(deps-dev): Bump sharp from 0.34.5 to 0.35.4"、"bump hono from 4.6.1 to 4.7.0 in /apps/api"
const SINGLE_BUMP = /^(?:[a-z]+(?:\([^)]*\))?!?:\s*)?bump (\S+) from (\S+) to (\S+)(?: in \S+)?$/i;
const VERSION = /^v?(\d+)\.(\d+)\.(\d+)$/;

const parseVersion = (v) => VERSION.exec(v)?.slice(1).map(Number) ?? null;

// 1.0 以上：同一个大版本内的 minor / patch 算兼容。
// 0.x 的 minor 就是不兼容升级（比如 sharp 0.34 → 0.35），只放行 patch；0.0.x 任何改动都不放行。
export function bumpKind(from, to) {
  const a = parseVersion(from);
  const b = parseVersion(to);
  if (!a || !b) return 'unknown';
  const i = a.findIndex((n, k) => n !== b[k]);
  if (i === -1) return 'unknown';
  if (b[i] < a[i]) return 'downgrade';
  const stable = a[0] >= 1 ? 1 : a[1] >= 1 ? 2 : 3;
  return i >= stable ? 'compatible' : 'breaking';
}

const KIND_REASON = {
  breaking: '是不兼容升级，需要人看（以后交给 Claude 改代码）',
  downgrade: '是降级，需要人看',
  unknown: '版本号不是普通的 x.y.z，需要人看',
};

export function decide(pr, { headSha, defaultBranch }) {
  const skip = (reason) => ({ merge: false, reason });
  if (pr.state !== 'OPEN') return skip(`PR 状态是 ${pr.state}，不是打开的`);
  if (pr.author?.login !== PR_AUTHOR) return skip('PR 不是 Dependabot 开的');
  if (!pr.headRefName?.startsWith('dependabot/')) return skip('分支不是 dependabot/ 开头');
  if (pr.baseRefName !== defaultBranch) return skip(`目标分支是 ${pr.baseRefName}，不是 ${defaultBranch}`);
  if (pr.headRefOid !== headSha) return skip('CI 测的不是 PR 最新的提交');
  const commits = pr.commits ?? [];
  const onlyBot = commits.length > 0 && commits.every((c) => c.authors?.length && c.authors.every((a) => a.login === COMMIT_AUTHOR));
  if (!onlyBot) return skip('PR 里有不是 Dependabot 的提交，需要人看');
  const m = SINGLE_BUMP.exec(pr.title ?? '');
  if (!m) return skip('标题不是单个依赖的升级（可能是分组升级），需要人看');
  const [, name, from, to] = m;
  const kind = bumpKind(from, to);
  if (kind !== 'compatible') return skip(`${name} ${from} → ${to} ${KIND_REASON[kind]}`);
  return { merge: true, reason: `${name} ${from} → ${to} 是兼容升级` };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [file, headSha, defaultBranch] = process.argv.slice(2);
  if (!file || !headSha || !defaultBranch) {
    console.error('用法：node dependabot-automerge.mjs <pr.json> <head SHA> <默认分支>');
    process.exit(2);
  }
  const { merge, reason } = decide(JSON.parse(readFileSync(file, 'utf8')), { headSha, defaultBranch });
  console.log(`${merge ? 'merge' : 'skip'}: ${reason}`);
}
