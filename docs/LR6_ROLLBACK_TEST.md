# Lab 6 — Rollback Test Evidence

## Environment

- Branch: `feature/lr6-continuous-delivery`
- Environment: preproduction
- Deployment host: isolated preproduction VM

## Successful release before failure simulation

- Commit: `ed21db77673b64234032d0c7d840fe2bb3c8c085`
- API and PostgreSQL containers: healthy
- `/health`: passed
- `/version`: passed
- Release smoke test: all checks passed

## Failed release simulation

- Candidate image tag: `2d3e10bd8ac482e00572d44603a0f66aed6021aa`
- The application started, but `/version` returned HTTP 404.
- Post-deployment smoke checks failed.
- The release script returned a failure status.
- Automatic rollback restored the previous release:
  `ed21db77673b64234032d0c7d840fe2bb3c8c085`
- Smoke checks for the restored release passed.

## Manual rollback

Pending a second successful deployment and manual rollback verification.
