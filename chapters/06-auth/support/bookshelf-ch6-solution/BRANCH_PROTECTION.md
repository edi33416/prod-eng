# Branch protection for `main`

The CI workflow is only a gate if GitHub refuses to merge when it fails.
Configure this once per repository, **after** `ci.yml` has run at least once on
`main` (GitHub only offers check names it has seen in the past week).

## Settings → Branches → classic branch protection rule for `main`

| Setting | Value |
|---|---|
| Require a pull request before merging | on |
| ↳ Require approvals | 1 (0 if you work alone; authors cannot approve their own PRs) |
| ↳ Dismiss stale pull request approvals when new commits are pushed | on |
| Require status checks to pass before merging | on |
| ↳ Require branches to be up to date before merging | on |
| ↳ Required checks | `lint`, `test`, `test-pg`, `build` |
| Require conversation resolution before merging | on |
| Require linear history | on |
| Do not allow bypassing the above settings | on |
| Allow force pushes / Allow deletions | off |

## Settings → Environments

| Environment | Protection |
|---|---|
| `staging` | Deployment branches: `main` |
| `production` | Required reviewers: at least one person · Deployment branches: `main` |

Both environments need a `DEPLOY_TOKEN` secret (environment-level, or one
repository-level secret shared by both).

## Things that silently break required checks

- **Renaming a job** (`name:`): the rule keeps waiting for the old name.
  Update the rule in the same change.
- **Adding a matrix**: `test` becomes `test (3.11)`, `test (3.12)`, …
- **Workflow-level `paths` / `paths-ignore`**: PRs that do not trigger the
  workflow never report the required checks and cannot be merged.
