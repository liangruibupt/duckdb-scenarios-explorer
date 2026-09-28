import assert from 'node:assert/strict';
import { test } from 'node:test';
import { bumpKind, decide } from './dependabot-automerge.mjs';

const SHA = '9ad3af8f00000000000000000000000000000000';
const OPTS = { headSha: SHA, defaultBranch: 'main' };

// 按 Dependabot 真实 PR #1（sharp 0.34.5 → 0.35.4）的 gh pr view 输出裁剪
const pr = (overrides = {}) => ({
  number: 1,
  state: 'OPEN',
  author: { is_bot: true, login: 'app/dependabot' },
  baseRefName: 'main',
  headRefName: 'dependabot/npm_and_yarn/sharp-0.35.4',
  headRefOid: SHA,
  title: 'build(deps-dev): Bump sharp from 0.34.5 to 0.35.4',
  commits: [{ oid: SHA, authors: [{ login: 'dependabot[bot]' }] }],
  ...overrides,
});

test('bumpKind treats minor and patch as compatible from 1.0 up', () => {
  assert.equal(bumpKind('1.2.3', '1.2.4'), 'compatible');
  assert.equal(bumpKind('1.2.3', '1.9.0'), 'compatible');
  assert.equal(bumpKind('v4.17.20', 'v4.17.21'), 'compatible');
  assert.equal(bumpKind('1.2.3', '2.0.0'), 'breaking');
});

test('bumpKind treats a 0.x minor as breaking and every 0.0.x change as breaking', () => {
  assert.equal(bumpKind('0.35.4', '0.35.5'), 'compatible');
  assert.equal(bumpKind('0.34.5', '0.35.4'), 'breaking');
  assert.equal(bumpKind('0.9.1', '1.0.0'), 'breaking');
  assert.equal(bumpKind('0.0.1', '0.0.2'), 'breaking');
});

test('bumpKind refuses downgrades, prereleases and unparsable versions', () => {
  assert.equal(bumpKind('1.2.4', '1.2.3'), 'downgrade');
  assert.equal(bumpKind('1.2.3', '1.2.3'), 'unknown');
  assert.equal(bumpKind('1.2.3', '1.3.0-rc.1'), 'unknown');
  assert.equal(bumpKind('1.2', '1.3'), 'unknown');
});

test('the real sharp 0.34 → 0.35 PR is left for a human', () => {
  const { merge, reason } = decide(pr(), OPTS);
  assert.equal(merge, false);
  assert.match(reason, /不兼容/);
});

test('a compatible single-dependency bump is merged', () => {
  for (const title of [
    'build(deps-dev): Bump sharp from 0.35.4 to 0.35.5',
    'build(deps): bump hono from 4.6.1 to 4.7.0 in /apps/api',
    'Bump lodash from 4.17.20 to 4.17.21',
  ]) {
    const { merge, reason } = decide(pr({ title }), OPTS);
    assert.equal(merge, true, title);
    assert.match(reason, /兼容升级/);
  }
});

test('grouped and multi-dependency titles are left for a human', () => {
  for (const title of [
    'build(deps): Bump the npm_and_yarn group across 2 directories with 3 updates',
    'build(deps-dev): Bump vite and vitest',
  ]) {
    assert.equal(decide(pr({ title }), OPTS).merge, false, title);
  }
});

test('a PR someone else pushed to is left for a human', () => {
  const commits = [
    { oid: 'a', authors: [{ login: 'dependabot[bot]' }] },
    { oid: SHA, authors: [{ login: 'liangruibupt' }] },
  ];
  const { merge, reason } = decide(pr({ title: 'Bump a from 1.0.0 to 1.0.1', commits }), OPTS);
  assert.equal(merge, false);
  assert.match(reason, /不是 Dependabot 的提交/);
  assert.equal(decide(pr({ title: 'Bump a from 1.0.0 to 1.0.1', commits: [] }), OPTS).merge, false);
});

test('only an open Dependabot PR into the default branch, at the SHA CI tested, is merged', () => {
  const ok = { title: 'Bump a from 1.0.0 to 1.0.1' };
  assert.equal(decide(pr(ok), OPTS).merge, true);
  assert.equal(decide(pr({ ...ok, state: 'MERGED' }), OPTS).merge, false);
  assert.equal(decide(pr({ ...ok, author: { is_bot: false, login: 'liangruibupt' } }), OPTS).merge, false);
  assert.equal(decide(pr({ ...ok, headRefName: 'feature/x' }), OPTS).merge, false);
  assert.equal(decide(pr({ ...ok, baseRefName: 'release' }), OPTS).merge, false);
  assert.equal(decide(pr({ ...ok, headRefOid: 'f'.repeat(40) }), OPTS).merge, false);
});
