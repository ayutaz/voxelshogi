"""Internal worker. Invoke through training's resource-bounded CLI."""

import json
import sys
from pathlib import Path

import pyarrow as pa

from .data import (
    GenerationConfig,
    _atomic_bytes,
    canonical,
    generate_dataset,
    validate_dataset,
)


def main():
    directory, raw, report, mode = sys.argv[1:]
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    config = GenerationConfig(**json.loads(raw))
    if mode == "generate":
        generate_dataset(Path(directory), config)
    elif mode != "validate":
        raise ValueError("unknown worker mode")
    result = validate_dataset(Path(directory))
    _atomic_bytes(Path(report), (canonical(result) + "\n").encode())


if __name__ == "__main__":
    main()
