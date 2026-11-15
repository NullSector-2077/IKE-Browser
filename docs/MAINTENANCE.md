# Maintenance policy

## Daily schedule

The repository health workflow is scheduled for 08:00 Europe/Rome. GitHub Actions schedules use UTC, so the workflow is triggered at both 06:00 and 07:00 UTC and checks the Europe/Rome local hour before doing its work. This accommodates both daylight-saving time and standard time without changing the intended local run time.

The workflow is observational: it checks repository structure and documentation consistency. It does not publish releases, sign packages, push to main, or silently change dependencies.

## Dependency maintenance

Automated dependency updates are not enabled in this bootstrap repository because the application source, dependency manifests and component update tooling have not yet been imported and reviewed.

After source import, component checks may be added for the exact dependencies that the project actually uses. Any automated update must:
- be limited to explicitly identified dependency files;
- use lockfiles and reproducible build settings where available;
- run the relevant tests and packaging checks;
- create a candidate branch and pull request;
- never merge itself into main or publish a release.

## Branch and review policy

- main is the protected stable line.
- Work is proposed through pull requests.
- Automated maintenance must use a dedicated branch.
- A draft PR remains draft until checks pass and a human reviews the changes.
- Failed, incomplete or skipped checks must not be described as passing.

## Signing and publication

Release signing is a local maintainer operation. Private signing keys must never enter Git, workflow artifacts, Actions logs or repository files.

A release is published only after the maintainer has tested the exact package on CachyOS and verified its signature and installed behavior.
