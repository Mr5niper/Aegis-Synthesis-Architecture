# scripts/patch_chrono.py
#
# Build helper for the Vulkan (from-source) llama-cpp-python compile in
# BUILD_EXE.bat. The pinned 0.3.2-era llama.cpp fails to compile against the
# newer Windows SDK (26100) + MSVC 17.13+ because two of its vendor C++ files
# use std::chrono without including <chrono> (older SDKs pulled it in
# transitively; the new one does not - llama.cpp issue 11834). This prepends the
# missing include to just those two files.
#
# This replaces an inline PowerShell loop in the batch script. Doing it in the
# already-verified build Python avoids spinning up PowerShell/.NET, reads and
# writes each file once (atomic in memory), and is easy to read and maintain.
#
# Idempotent: if the include is already present, the file is left untouched.
# Usage:  python scripts/patch_chrono.py <llama_cpp_source_root>
# Exit code 0 on success (including "already patched"), 1 on any error.
import os
import sys

INCLUDE_LINE = "#include <chrono>"
TARGET_FILES = ("common.cpp", "log.cpp")


def patch_one(path: str) -> bool:
    """Prepend the chrono include to `path` if missing. Returns True on success
    (patched or already-present), False if the file is missing or unwritable."""
    if not os.path.isfile(path):
        print("[ERROR] expected source file not found: %s" % path)
        return False
    try:
        with open(path, "r", encoding="utf-8", errors="surrogatepass") as f:
            text = f.read()
    except Exception as e:
        print("[ERROR] could not read %s: %s" % (path, e))
        return False

    if INCLUDE_LINE in text:
        print("[INFO]   already patched: %s" % os.path.basename(path))
        return True

    try:
        # Write once: the include, a newline, then the original content.
        with open(path, "w", encoding="utf-8", errors="surrogatepass", newline="") as f:
            f.write(INCLUDE_LINE + "\n" + text)
    except Exception as e:
        print("[ERROR] could not write %s: %s" % (path, e))
        return False

    print("[INFO]   patched: %s" % os.path.basename(path))
    return True


def main(argv) -> int:
    if len(argv) != 2:
        print("Usage: python scripts/patch_chrono.py <llama_cpp_source_root>")
        return 1
    src_root = argv[1]
    common_dir = os.path.join(src_root, "vendor", "llama.cpp", "common")
    ok = True
    for name in TARGET_FILES:
        if not patch_one(os.path.join(common_dir, name)):
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
