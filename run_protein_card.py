"""Separate offline GFP card launcher; does not modify the v1 case workflow."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from traitweaver.protein_card import main

if __name__ == '__main__':
    sys.exit(main())
