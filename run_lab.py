"""Run directly from a source checkout; no installation or dependencies needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from edge_inference_lab.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
