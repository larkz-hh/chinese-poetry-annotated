"""Merge annotation records through the staged v3 builder, refreshing all derived data."""
import sys
from rebuild import main

if __name__ == "__main__":
    sys.argv.insert(1, "--app-only")
    main()
