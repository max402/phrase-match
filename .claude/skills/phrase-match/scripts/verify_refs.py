#!/usr/bin/env python3
"""Verify that reference URLs are alive before they are cited.

Every URL the skill cites must pass through this script — the model is
never allowed to cite a URL it has not seen verified.

Usage:
  verify_refs.py URL [URL ...]        # check specific URLs
  verify_refs.py --from-data          # check every source URL in idioms.json

Exit codes: 0 = all URLs alive, 1 = at least one dead or unreachable.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import iter_source_urls, load_data

TIMEOUT_S = 15
USER_AGENT = "phrase-match/1.0 (reference checker; +https://github.com/max402/phrase-match)"


def encode_url(url: str) -> str:
    """Percent-encode non-ASCII path/query characters (Cyrillic URLs)."""
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%")
    query = urllib.parse.quote(parts.query, safe="=&?+%")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def check(url: str) -> tuple[bool, str]:
    """Return (alive, status). Tries HEAD first, falls back to GET."""
    encoded = encode_url(url)
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(encoded, method=method, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                return True, str(response.status)
        except urllib.error.HTTPError as err:
            if method == "HEAD" and err.code in (403, 405):
                continue  # some servers reject HEAD; retry with GET
            return False, str(err.code)
        except (urllib.error.URLError, TimeoutError) as err:
            return False, f"unreachable ({getattr(err, 'reason', err)})"
    return False, "unreachable"


def main() -> int:
    """Parse CLI arguments, check each URL once, report the results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*", help="URLs to verify")
    parser.add_argument(
        "--from-data", action="store_true", help="verify every source URL found in idioms.json"
    )
    parser.add_argument("--data", type=Path, default=None, help="path to idioms.json")
    args = parser.parse_args()

    targets: list[tuple[str, str]] = [(u, "cli") for u in args.urls]
    if args.from_data:
        targets += list(iter_source_urls(load_data(args.data)))
    if not targets:
        parser.error("give URLs as arguments or use --from-data")

    seen: set[str] = set()
    failures = 0
    for url, location in targets:
        if url in seen:
            continue
        seen.add(url)
        alive, status = check(url)
        if alive:
            print(f"OK   {status:>5}  {url}")
        else:
            print(f"DEAD {status:>5}  {url}   [{location}]")
            failures += 1

    print(f"\n{len(seen) - failures}/{len(seen)} URLs alive.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
