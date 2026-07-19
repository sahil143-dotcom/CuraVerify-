"""Hugging Face Spaces entrypoint — runs the scientific Streamlit product demo."""
from pathlib import Path
import runpy

_DEMO = Path(__file__).resolve().parent / "scientific" / "app.py"
runpy.run_path(str(_DEMO), run_name="__main__")
