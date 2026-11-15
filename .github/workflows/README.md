# CI workflow

The GitHub Actions checks run on the hosted Ubuntu 24.04 64-bit runner.
This is a Linux CI environment, not physical Raspberry Pi hardware or an ARM
runner.

| Trigger | Actions performed | Explanation |
|---|---|---|
| Local commit | When installed with `pre-commit install`, the local hook runs Ruff linting/formatting, TOML/YAML validation, end-of-file and whitespace checks, Codespell, and README table-of-contents maintenance. Proselint is available only as a manual hook. | Fast checks give feedback before changes are pushed. Tests and package builds are not run by the local hooks. |
| Pull request | Runs the pre-commit checks, pytest with coverage on Python 3.11, 3.12, 3.13, and 3.14, the DGB startup smoke test in that matrix, Python 3.13 MQTT startup/configuration smoke tests against local Mosquitto, and a wheel/source distribution build with `twine check`. | These checks are intended to be required before merging. The smoke tests observe DGB behaviour through MQTT; no Home Assistant, real GPIO, public broker, or broker authentication is used. |
| Push to `main` or a `v*` tag | Runs the same pre-commit, Python test matrix, Python 3.13 MQTT smoke tests, and package build/check as a pull request. | Keeps the default branch and version-tag builds subject to the same quality checks. |
| Published GitHub Release | Runs the standard checks above and verifies the release assets by downloading, installing, and importing one wheel and one source distribution. | The verification job checks assets already attached to the Release; it does not create or upload release assets. |
| Python 3.13 test job | Saves the coverage XML report as the `coverage-report-python-3.13` workflow artifact for 30 days. | Coverage is retained for inspection without granting CI permission to write to the repository or README. |

The smoke broker is temporary and uses Mosquitto's default anonymous,
localhost-only listener. Authentication is intentionally not tested: the smoke
tests observe the MQTT discovery messages produced by DGB.

Repository branch protection and required-check settings are configured separately
from this workflow.
