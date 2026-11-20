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

- Second successful release: `9d051f3f674a53287c30d1e27cfccc955e74739d`
- Previous successful release recorded: `ed21db77673b64234032d0c7d840fe2bb3c8c085`
- Executed manually using `fishing-preprod-release rollback`.
- The script restored the previous image from the local Docker cache.
- All post-deployment smoke checks passed.
- `/version` confirmed the restored commit `ed21db77673b64234032d0c7d840fe2bb3c8c085`.
- API and PostgreSQL containers were both healthy.
- The previous-tag state was updated to the rolled-back-from release:
  `9d051f3f674a53287c30d1e27cfccc955e74739d`

## Conclusion

Both automatic rollback after a failed release and manual rollback to the
previous successful release were tested successfully in pre-production.
