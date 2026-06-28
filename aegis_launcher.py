# aegis_launcher.py
# PyInstaller entry point. We do NOT use src/main_gui.py directly as the entry
# script because it relies on package-relative imports (from .core ... ), which
# only work when it is imported as part of the `src` package — not when run as a
# top-level script. This launcher imports the package properly and calls main().
from src.main_gui import main

if __name__ == "__main__":
    main()
