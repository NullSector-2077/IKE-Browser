import sys

from . import early_args

early_args(sys.argv[1:])

from .app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
