"""Pytest configuration for Serena tools tests."""
import sys
from pathlib import Path

# Add skills/serena directory to Python path so tools can be imported as a package
serena_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(serena_dir))
