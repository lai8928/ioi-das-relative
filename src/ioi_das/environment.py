"""Inspect the selected interpreter and optionally require a real CUDA operation."""

from importlib import metadata
import os
import platform
import sys


def inspect_environment(require_gpu: bool = False, device: str = "cuda:0") -> dict:
    """Check dependencies and verify CUDA with a small matrix multiplication.

    This diagnostic loads no language model and performs no DAS training.
    GPU verification fails explicitly instead of falling back to CPU.
    """
    packages = {}
    for name in ("torch", "transformers", "tokenizers", "pyvene", "numpy", "pytest", "packaging", "pip"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    missing = [name for name in ("transformers", "tokenizers", "pytest") if packages[name] is None]
    report = {
        "executable": sys.executable,
        "prefix": sys.prefix,
        "python": platform.python_version(),
        "packages": packages,
        "missing_phase1_test_dependencies": missing,
        "phase1_dependency_status": "ready" if not missing else "missing_dependencies",
        "environment_variables": {key: os.environ.get(key) for key in
                                  ("CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CUDA_VISIBLE_DEVICES")},
        "gpu_required": require_gpu,
        "gpu": {"status": "not_checked"},
        "model_weights_loaded": False,
        "das_training_started": False,
    }
    if require_gpu:
        gpu = {"requested_device": device, "status": "failed"}
        report["gpu"] = gpu
        try:
            import torch

            gpu["torch_cuda_runtime"] = torch.version.cuda
            gpu["cuda_available"] = torch.cuda.is_available()
            gpu["visible_device_count"] = torch.cuda.device_count()
            if not gpu["cuda_available"]:
                raise RuntimeError("PyTorch cannot access CUDA. Check GPU allocation, "
                                   "driver/device access, CUDA_VISIBLE_DEVICES, and the CUDA-enabled PyTorch build.")
            selected = torch.device(device)
            if selected.type != "cuda":
                raise ValueError("GPU verification requires a CUDA device, for example cuda:0.")
            index = selected.index if selected.index is not None else torch.cuda.current_device()
            if not 0 <= index < gpu["visible_device_count"]:
                raise ValueError(f"CUDA device index {index} is outside the visible device range.")
            selected = torch.device("cuda", index)
            properties = torch.cuda.get_device_properties(selected)
            gpu.update({"logical_device_index": index, "device_name": properties.name,
                        "total_memory_bytes": properties.total_memory,
                        "compute_capability": [properties.major, properties.minor]})
            with torch.no_grad():
                matrix = torch.ones((256, 256), dtype=torch.float32, device=selected)
                result = matrix @ matrix
                torch.cuda.synchronize(selected)
                if not result.is_cuda or result.device != selected or not bool(torch.all(result == 256).item()):
                    raise RuntimeError("CUDA matrix multiplication failed device or result validation.")
                gpu["smoke_test"] = {"operation": "256x256 float32 matrix multiplication",
                                     "input_device": str(matrix.device), "result_device": str(result.device),
                                     "expected_each_element": 256, "observed_first_element": result[0, 0].item(),
                                     "all_elements_correct": True,
                                     "allocated_memory_bytes": torch.cuda.memory_allocated(selected)}
            gpu["status"] = "passed"
        except (ImportError, OSError, RuntimeError, ValueError, AssertionError) as error:
            gpu["error"] = f"{type(error).__name__}: {error}"
    report["status"] = "passed" if not missing and (not require_gpu or report["gpu"]["status"] == "passed") else "failed"
    return report
