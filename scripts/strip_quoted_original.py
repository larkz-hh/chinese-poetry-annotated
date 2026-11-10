"""Compatibility entry: quote cleanup is part of the v3 staged build."""
import sys
from rebuild import main

if __name__ == "__main__":
    sys.argv.insert(1, "--app-only")
    main()
