# src/utils/hardware.py
#
# Runtime hardware detection so Aegis adapts to whatever machine it runs on,
# instead of the previous hardcoded n_gpu_layers=0 and fixed thread count.
#
# What this can and cannot do, stated honestly:
#   - It CAN measure system RAM, CPU thread count, and detect whether a GPU is
#     present (and how much VRAM), best-effort, with no hard dependencies.
#   - It CAN pick good values for n_threads, n_ctx, and n_gpu_layers.
#   - It CANNOT make llama-cpp-python use a GPU the installed build was not
#     compiled for. GPU offload only happens if the llama_cpp wheel was built
#     with a GPU backend (CUDA / Metal / Vulkan / ROCm). On a CPU-only wheel,
#     n_gpu_layers is ignored by llama.cpp. See gpu_backend_available().
#
# Every probe is wrapped so any failure falls back to safe CPU-only defaults
# and the app still runs.

from __future__ import annotations
import os
import platform
import subprocess
from dataclasses import dataclass


@dataclass
class HardwareProfile:
    cpu_threads: int
    total_ram_gb: float
    gpu_vendor: str          # "nvidia" | "amd" | "apple" | "intel" | "none"
    gpu_vram_gb: float       # 0.0 if unknown/none
    llama_gpu_backend: str   # "cuda" | "metal" | "vulkan" | "rocm" | "cpu" | "unknown"

    @property
    def has_usable_gpu(self) -> bool:
        # Usable only if a device exists AND llama_cpp was built with a GPU backend.
        return self.gpu_vendor != "none" and self.llama_gpu_backend not in ("cpu", "unknown")


def _detect_cpu_threads() -> int:
    try:
        n = os.cpu_count() or 2
    except Exception:
        n = 2
    # Leave a core for the UI/OS; never below 2.
    return max(2, n - 1)


def _detect_total_ram_gb() -> float:
    try:
        import psutil  # type: ignore
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round((pages * page_size) / (1024 ** 3), 1)
    except Exception:
        pass
    try:
        import ctypes

        class _MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return round(stat.ullTotalPhys / (1024 ** 3), 1)
    except Exception:
        pass
    return 8.0  # conservative unknown default


def _run(cmd) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return (out.stdout or "") + (out.stderr or "")
    except Exception:
        return ""


def _detect_gpu() -> tuple[str, float]:
    """Return (vendor, vram_gb). Best-effort, never raises."""
    sysname = platform.system()

    # Apple Silicon: unified memory, Metal GPU present on arm64 Macs.
    if sysname == "Darwin":
        try:
            if platform.machine() in ("arm64", "aarch64"):
                # Unified memory: treat a fraction of RAM as usable VRAM.
                return "apple", 0.0
        except Exception:
            pass

    # NVIDIA: nvidia-smi is the reliable signal.
    smi = _run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"])
    if smi.strip():
        try:
            mb = max(int(x) for x in smi.split() if x.strip().isdigit())
            return "nvidia", round(mb / 1024, 1)
        except Exception:
            return "nvidia", 0.0

    # Windows: query WMI for the video controller name to identify vendor.
    if sysname == "Windows":
        name = _run(["wmic", "path", "win32_VideoController", "get", "name"]).lower()
        if not name:
            # wmic is deprecated on newer Windows; try PowerShell CIM.
            name = _run([
                "powershell", "-NoProfile", "-Command",
                "(Get-CimInstance Win32_VideoController).Name"
            ]).lower()
        if "nvidia" in name or "geforce" in name or "quadro" in name or "rtx" in name:
            return "nvidia", 0.0
        if "amd" in name or "radeon" in name:
            return "amd", 0.0
        if "intel" in name and ("arc" in name or "iris" in name or "graphics" in name):
            return "intel", 0.0

    # Linux: lspci vendor scan.
    if sysname == "Linux":
        lspci = _run(["lspci"]).lower()
        if "nvidia" in lspci:
            return "nvidia", 0.0
        if "amd" in lspci or "radeon" in lspci or "advanced micro devices" in lspci:
            return "amd", 0.0
        if "intel" in lspci and ("arc" in lspci or "graphics" in lspci):
            return "intel", 0.0

    return "none", 0.0


def _detect_llama_backend() -> str:
    """Best-effort: which backend was llama_cpp compiled with.

    llama-cpp-python does not expose this cleanly, so we probe a few signals.
    Unknown is treated as CPU (we won't promise GPU offload we can't deliver).
    """
    try:
        import llama_cpp  # type: ignore
    except Exception:
        return "unknown"

    # Newer llama_cpp exposes supports_gpu_offload() via the C API binding.
    for attr in ("llama_supports_gpu_offload",):
        try:
            fn = getattr(llama_cpp.llama_cpp, attr, None)
            if fn and bool(fn()):
                # A GPU backend is compiled in; identify which by env/name hints.
                name = (getattr(llama_cpp, "__version__", "") or "").lower()
                for tag in ("cuda", "metal", "vulkan", "rocm"):
                    if tag in name:
                        return tag
                return "vulkan"  # generic GPU backend present, vendor-agnostic
        except Exception:
            pass
    return "cpu"


def detect_hardware() -> HardwareProfile:
    threads = _detect_cpu_threads()
    ram = _detect_total_ram_gb()
    vendor, vram = _detect_gpu()
    backend = _detect_llama_backend()
    return HardwareProfile(
        cpu_threads=threads,
        total_ram_gb=ram,
        gpu_vendor=vendor,
        gpu_vram_gb=vram,
        llama_gpu_backend=backend,
    )


def plan_model_params(hw: HardwareProfile, requested_ctx: int, n_gpu_layers_cfg: int) -> dict:
    """Turn a hardware profile into concrete llama.cpp params.

    - n_gpu_layers: if config forces a value (>0 or -1) and a GPU backend is
      usable, respect it. If config is 0 (auto) and a usable GPU exists, offload
      all layers (-1). Otherwise 0 (CPU).
    - n_ctx: keep the model's requested context, but clamp down on low-RAM
      machines so we do not thrash or OOM.
    - n_threads: from CPU detection.
    """
    # GPU layers
    if not hw.has_usable_gpu:
        n_gpu_layers = 0
    elif n_gpu_layers_cfg and n_gpu_layers_cfg != 0:
        n_gpu_layers = n_gpu_layers_cfg  # explicit override (incl. -1 = all)
    else:
        n_gpu_layers = -1  # auto: offload everything to the usable GPU

    # Context clamp by RAM (CPU inference holds the KV cache in RAM).
    n_ctx = requested_ctx
    if not hw.has_usable_gpu:
        if hw.total_ram_gb <= 8:
            n_ctx = min(requested_ctx, 2048)
        elif hw.total_ram_gb <= 16:
            n_ctx = min(requested_ctx, 4096)
        # >16 GB: honor whatever the model requested.

    return {
        "n_ctx": n_ctx,
        "n_threads": hw.cpu_threads,
        "n_gpu_layers": n_gpu_layers,
    }


def describe(hw: HardwareProfile) -> str:
    gpu = "none" if hw.gpu_vendor == "none" else hw.gpu_vendor
    vram = f", ~{hw.gpu_vram_gb} GB VRAM" if hw.gpu_vram_gb else ""
    usable = "usable for offload" if hw.has_usable_gpu else "NOT used (llama_cpp is CPU-only build)"
    if hw.gpu_vendor == "none":
        usable = "no GPU detected"
    return (
        f"CPU threads: {hw.cpu_threads} | RAM: {hw.total_ram_gb} GB | "
        f"GPU: {gpu}{vram} | llama backend: {hw.llama_gpu_backend} ({usable})"
    )
