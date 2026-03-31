import sys

__version__ = "1.2.4.2"

if sys.version_info < (3, 13):
    raise RuntimeError(
        f"Agency requires Python 3.13 or later. "
        f"You are running Python {sys.version_info.major}.{sys.version_info.minor}. "
        f"If you installed with pipx, reinstall with: "
        f"pipx install --python python3.13 agency-engine"
    )
