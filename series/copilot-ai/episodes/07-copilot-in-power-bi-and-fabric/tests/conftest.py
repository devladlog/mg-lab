import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EPISODE = HERE.parent
sys.path.insert(0, str(EPISODE / "src"))

SERIES = EPISODE.parent.parent.parent  # .../series
CATEGORY_MODEL = SERIES / "power-bi" / "episodes" / "01-data-modeling-star-schema" / "src" / "ContosoSales.SemanticModel"
STAR = SERIES / "power-bi" / "episodes" / "01-data-modeling-star-schema" / "src" / "data" / "star"
DATA = EPISODE / "src" / "data"
