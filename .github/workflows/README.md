# CI workflow

The GitHub Actions checks run on the hosted Ubuntu 24.04 64-bit runner.
This is a Linux CI environment, not physical Raspberry Pi hardware or an ARM
runner.

| Trigger | Actions performed | Explanation |
|---|---|---|
| Local commit | When installed with `pre-commit install`, the local hook runs Ruff linting/formatting, TOML/YAML validation, end-of-file and whitespace checks, Codespell, and README table-of-contents maintenance. Proselint and Lychee's external URL check are available only as manual hooks. | Fast checks give feedback before changes are pushed. Tests and package builds are not run by the local hooks. Run the optional URL check with `pre-commit run --hook-stage manual lychee --all-files`. |
| Pull request | Runs workflow syntax/security checks (`actionlint` and `zizmor`), an offline local Markdown-link/anchor check, pre-commit, pytest with coverage on Python 3.11, 3.12, 3.13, and 3.14, the DGB startup smoke test in that matrix, Python 3.13 MQTT startup/configuration smoke tests against local Mosquitto, and a wheel/source distribution build with `twine check`. | These checks are intended to be required before merging. External URLs are not queried by CI. The MQTT smoke observes DGB behaviour; no Home Assistant, real GPIO, public broker, or broker authentication is used. |
| Published GitHub Release | Retains the release trigger, runs the standard validation checks, and verifies the release assets by downloading, installing, and importing one wheel and one source distribution. | The verification job checks assets already attached to the Release; it does not create or upload release assets. |
| Python 3.13 test job | Saves the coverage XML report as the `coverage-report-python-3.13` workflow artifact for 30 days. | Coverage is retained for inspection without granting CI permission to write to the repository or README. |

The smoke broker is temporary and uses Mosquitto's default anonymous,
localhost-only listener. Authentication is intentionally not tested: the smoke
tests observe the MQTT discovery messages produced by DGB.

Repository branch protection and required-check settings are configured separately
from this workflow.

The workflow runs on pull requests and published Releases; it does not run on
ordinary branch or tag pushes. Action references use full commit SHAs, with the
upstream version in a comment. `.github/dependabot.yml` schedules monthly updates
for GitHub Actions and Python dependencies, so reviewable update pull requests
can keep these pins current.
