"""Entry point for python3 -m madd: hands control to the CLI in madd/cli.py."""

from .cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
