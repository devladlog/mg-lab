import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "py"))
import digest

budget = 0.29
print(f"Python:     int(0.29 * 100) = {int(budget * 100)}")
print(f"Python:     Decimal('0.29') -> {digest.to_cents(Decimal('0.29'))} cents (exact)")
# The deprecated float helper prints a DeprecationWarning on stderr:
print(f"Python:     to_cents_float(0.29) = {digest.to_cents_float(budget)}")
