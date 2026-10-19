#!/usr/bin/env python3
"""Standalone hardware detector for Axolotl Docking.

Runnable on its own (the installer calls it at the end, and `Docking hardware`
reuses the same logic):

    python3 scripts/detect_hardware.py            # human-readable report (Spanish)
    python3 scripts/detect_hardware.py --json      # machine-readable JSON

Standard library only, so it works before the conda environment exists.
"""
import json
import os
import sys

# make the app package importable when run directly from a clone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from axd import hardware as H          # noqa: E402
from axd import thermal as T           # noqa: E402
from axd import tuning                 # noqa: E402


def main(argv):
    if "--json" in argv:
        hw = H.detect()
        out = {
            "hardware": hw.to_dict(),
            "plan": tuning.plan(hw).__dict__,
            "temperature": {"cpu_c": T.read_cpu_temp_c(), "gpu_c": T.read_gpu_temps_c()},
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    # pretty report (reuses the UI styling)
    from axd import hardware_report
    hardware_report.report(redetect="--redetect" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
