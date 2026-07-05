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


def _windows_gpu_vram_gb() -> float:
    r"""Best-effort read of the primary GPU's dedicated VRAM on Windows, in GB.

    Win32_VideoController.AdapterRAM is a 32-bit signed field that saturates at
    ~4 GB and misreports larger cards, so we do NOT trust it for modern GPUs.
    The reliable value is the 64-bit qwMemorySize the driver writes to the
    registry under each display adapter's key
    (HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-...}\000x ->
    HardwareInformation.qwMemorySize). We take the largest across adapters.
    Returns 0.0 on any failure (caller then falls back to RAM-based sizing).
    """
    ps = (
        r"$vals = Get-ItemProperty "
        r"'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\*' "
        r"-ErrorAction SilentlyContinue | "
        r"ForEach-Object { $_.'HardwareInformation.qwMemorySize' } | "
        r"Where-Object { $_ -ne $null }; "
        r"if ($vals) { ($vals | Measure-Object -Maximum).Maximum }"
    )
    out = _run(["powershell", "-NoProfile", "-Command", ps])
    try:
        # The value is bytes; take the largest integer token in the output.
        nums = [int(t) for t in out.replace("\r", " ").split() if t.strip().isdigit()]
        if nums:
            return round(max(nums) / (1024 ** 3), 1)
    except Exception:
        pass
    return 0.0


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
        # Read dedicated VRAM once (64-bit registry value); 0.0 if unavailable.
        vram = _windows_gpu_vram_gb()
        if "nvidia" in name or "geforce" in name or "quadro" in name or "rtx" in name:
            return "nvidia", vram
        if "amd" in name or "radeon" in name:
            return "amd", vram
        if "intel" in name and ("arc" in name or "iris" in name or "graphics" in name):
            return "intel", vram

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


def plan_model_params(hw: HardwareProfile, requested_ctx: int, n_gpu_layers_cfg: int,
                      ctx_train_max: int = 0, concurrent_models: int = 1) -> dict:
    """Turn a hardware profile into concrete llama.cpp params.

    - n_gpu_layers: if config forces a value (>0 or -1) and a GPU backend is
      usable, respect it. If config is 0 (auto) and a usable GPU exists, offload
      all layers (-1). Otherwise 0 (CPU).
    - n_ctx: auto-scaled to the machine. The config ctx_size is a BASELINE
      floor (never reduced below it, only raised), and the result is capped by
      ctx_train_max (the model's trained context length) when known. The
      capability signal depends on the build: a GPU-offload build sizes by
      VRAM (the KV cache lives in VRAM), a CPU build sizes by system RAM. If a
      GPU is present but its VRAM cannot be read, a conservative fixed ceiling
      is used instead of RAM (which would over-size and OOM the card). The
      chosen ceiling, the reason, and any fallback are printed to the console.
    - concurrent_models: how many models are held resident at the same time.
      On a GPU build ALL registered models live in VRAM simultaneously, so the
      per-model VRAM budget is the card's VRAM divided by this count. Sizing
      each model as if it owned the whole card is what OOM'd a 12 GB card once
      a 3B and a 7B were both loaded. Defaults to 1.
    - n_threads: from CPU detection.
    """
    # GPU layers
    if not hw.has_usable_gpu:
        n_gpu_layers = 0
    elif n_gpu_layers_cfg and n_gpu_layers_cfg != 0:
        n_gpu_layers = n_gpu_layers_cfg  # explicit override (incl. -1 = all)
    else:
        n_gpu_layers = -1  # auto: offload everything to the usable GPU

    # Context sizing. The correct capacity signal DEPENDS on where the KV cache
    # lives, and that differs between the two build types:
    #
    #   - GPU offload build: the KV cache lives in VRAM. So the ceiling MUST be
    #     governed by VRAM, NOT system RAM. Sizing off system RAM here is what
    #     caused an out-of-device-memory crash on a 12 GB card in a 128 GB box:
    #     RAM said "go huge", VRAM could not hold it.
    #   - CPU-only build: the KV cache lives in system RAM, so RAM is the right
    #     signal there.
    #
    # SAFETY PRINCIPLE (per design): whenever the correct signal is uncertain
    # (GPU present but VRAM unreadable, or any probe returns 0), we FALL BACK to
    # a conservative fixed ceiling rather than risk an OOM, and we PRINT which
    # branch was taken and why, so a later crash log shows the decision.
    #
    # ceiling is the largest context this machine will be handed. Final n_ctx is
    # max(configured baseline, ceiling) - a hand-set ctx_size is never reduced,
    # only raised - then capped by the model's trained max below.
    _reason = ""
    if hw.has_usable_gpu:
        # All resident models share the card, so each model's real budget is
        # the total VRAM divided by how many are loaded at once. Sizing against
        # the full card per-model is what OOM'd when a 3B and a 7B coexisted.
        n_models = max(1, concurrent_models)
        vram_total = hw.gpu_vram_gb
        vram = (vram_total / n_models) if vram_total else 0.0
        if vram and vram > 0:
            # VRAM-tiered ceiling, applied to the PER-MODEL budget. Tuned to
            # leave room for the model weights (a 3B-7B Q4_K_M is ~2-4.5 GB)
            # plus compute buffers alongside the KV cache on the same card.
            # Deliberately conservative: better a smaller window than a failed
            # load. Note the tiers are read against the per-model share, so a
            # 12 GB card with 2 models sizes each against ~6 GB.
            if vram <= 6:
                ceiling = 4096
            elif vram <= 8:
                ceiling = 8192
            elif vram <= 12:
                ceiling = 16384
            elif vram <= 16:
                ceiling = 24576
            elif vram <= 24:
                ceiling = 32768
            else:
                ceiling = 65536
            _reason = (f"GPU sizing by VRAM: {vram_total} GB / {n_models} model(s) "
                       f"= {round(vram, 1)} GB each -> ceiling {ceiling}")
        else:
            # GPU is usable but we could not read its VRAM (e.g. AMD/Intel where
            # the registry probe failed). Do NOT fall back to RAM-based sizing:
            # that over-sizes and OOMs the card. Use a safe fixed ceiling.
            ceiling = 8192
            _reason = ("GPU present but VRAM unknown (probe returned 0); "
                       f"using SAFE FALLBACK ceiling {ceiling}")
    else:
        # CPU-only build: KV cache is in system RAM, so RAM is the right signal.
        ram = hw.total_ram_gb
        if ram <= 8:
            ceiling = 4096
        elif ram <= 16:
            ceiling = 8192
        elif ram <= 32:
            ceiling = 16384
        elif ram <= 64:
            ceiling = 32768
        else:
            ceiling = 65536
        # Even with lots of RAM, CPU inference computes every token on the CPU,
        # so a huge window slows each turn. Hold the top tiers back a step.
        if ceiling > 8192:
            ceiling = max(8192, ceiling // 2)
        _reason = f"CPU sizing by RAM: {hw.total_ram_gb} GB -> ceiling {ceiling}"

    # Baseline from config is a floor: never go below what the user asked for.
    n_ctx = max(requested_ctx, ceiling)
    _floor_note = ""
    if requested_ctx > ceiling:
        _floor_note = f"; config baseline {requested_ctx} raises it above ceiling"

    # Never exceed the model's trained context length when we know it; going
    # past it produces degraded output. When unknown (0), do not scale above
    # the requested baseline to stay safe.
    _cap_note = ""
    if ctx_train_max and ctx_train_max > 0:
        if n_ctx > ctx_train_max:
            _cap_note = f"; capped to model trained max {ctx_train_max}"
        n_ctx = min(n_ctx, ctx_train_max)
    elif requested_ctx:
        if n_ctx > requested_ctx:
            _cap_note = (f"; model trained-max unknown, held at baseline "
                         f"{requested_ctx}")
        n_ctx = min(n_ctx, requested_ctx)

    # Always print the decision so crash logs show exactly how n_ctx was chosen
    # and, importantly, whether a safe fallback was used.
    print(f"[ctx] {_reason}{_floor_note}{_cap_note} => n_ctx={n_ctx}")

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
