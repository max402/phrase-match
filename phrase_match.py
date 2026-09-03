#!/usr/bin/env python3
"""Convenience entry point: look up a phrase from the repository root.

Thin wrapper around .claude/skills/phrase-match/scripts/lookup.py so that
collaborators do not have to type the full script path:

  python3 phrase_match.py --phrase "Не гони лошадей!" --target de

All arguments are forwarded unchanged; see `python3 phrase_match.py --help`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / ".claude/skills/phrase-match/scripts"))
from lookup import main

if __name__ == "__main__":
    sys.exit(main())
