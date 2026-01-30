import sys
from pathlib import Path


def _ensure_package_on_path() -> None:
    if __package__:
        return
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_package_on_path()

from operator_desktop.main import main


if __name__ == "__main__":
    raise SystemExiащопукщшпоущкпшо= ьфчfgdkbldgldf maks gay