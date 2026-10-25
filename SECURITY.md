# Security policy

## Supported versions

VoxelShogi is an experimental project. Security fixes target the latest `main` branch and the current public deployment. Older commits and exported builds are not maintained separately.

## Reporting a vulnerability

Please use [GitHub private vulnerability reporting](https://github.com/ayutaz/voxelshogi/security/advisories/new). Include the affected commit or URL, reproduction steps, and the expected impact. Do not include real credentials or another person's private data.

Please report security issues privately rather than opening a public issue. Ordinary bugs and rule questions can be reported in GitHub Issues. This project has no guaranteed response time; maintainers will coordinate a fix and disclosure through the private report.

## Credentials and dependencies

Never commit credentials, model checkpoints, or private game records. Local Cloudflare authentication must use `scripts/cf.sh`, which isolates this project's account from global Wrangler settings. Production credentials belong to GitHub's `production` environment.

Dependabot, dependency audits, CodeQL, secret scanning, and push protection are used alongside tests. Findings require review; a successful automated check is not a guarantee that all vulnerabilities are absent.
