#!/usr/bin/env bash
set -euo pipefail

uvx pip-licenses --format=markdown --with-urls > LICENSES.md
uvx pip-licenses --fail-on="GPL;AGPL"
