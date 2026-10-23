#!/usr/bin/env python3
"""Install a verified local precompiled release, independently of this checkout."""
import sys
from pathlib import Path

# Offline archive and online bootstrap share the release installer in precompiled.
if '--archive' in sys.argv or '--launch' in sys.argv:
    from precompiled import main
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from bootstrap import main

if __name__ == '__main__':
    raise SystemExit(main())
