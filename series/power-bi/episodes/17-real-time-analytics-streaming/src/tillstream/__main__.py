import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # the modules import each other by plain name
from cli import main  # noqa: E402

raise SystemExit(main())
