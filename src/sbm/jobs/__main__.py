"""`python -m sbm.jobs <letter>` — see `runner.main`."""

from __future__ import annotations

import sys

from sbm.jobs.runner import main

if __name__ == "__main__":
    sys.exit(main())
