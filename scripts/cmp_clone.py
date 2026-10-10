#!/usr/bin/env python3
"""Compare SansAmpClone renders with the PSA-1 reference renders.

The comparison uses the same dry reference for both plugins and removes the
shared baseline by measuring every file relative to its own cmin/min render.
"""
import os
import sys

import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from fit_drive import FREQS, h1_bands


ROOT = os.path.dirname(SCRIPT_DIR)
REF_DIR = os.path.join(ROOT, "ref", "drive")
CLONE_DIR = os.path.join(ROOT, "clone")


def response(path, dry_path):
    return h1_bands(dry_path, path, FREQS)


def compare_series(level, tags):
    dry = os.path.join(REF_DIR, f"drive_dry_{level}.wav")
    ref_base_path = os.path.join(REF_DIR, f"drive_cmin_min_{level}.wav")
    clone_base_path = os.path.join(CLONE_DIR, f"clone_drive_cmin_min_{level}.wav")

    required = [dry, ref_base_path, clone_base_path]
    required += [
        os.path.join(REF_DIR, f"drive_{tag}_{level}.wav")
        for tag in tags
    ]
    required += [
        os.path.join(CLONE_DIR, f"clone_drive_{tag}_{level}.wav")
        for tag in tags
    ]

    missing = [path for path in required if not os.path.exists(path)]
    if missing:
        print(f"\nPoziom {level}: BRAK PLIKÓW")
        for path in missing:
            print(f"  {path}")
        return False

    ref_base, ref_coh = response(ref_base_path, dry)
    clone_base, clone_coh = response(clone_base_path, dry)
    print(f"\n=== Poziom {level} ===")
    print("f [Hz]       " + " ".join(f"{f:7.0f}" for f in FREQS))
    print("baseline ref " + " ".join(f"{x:7.2f}" for x in ref_base))
    print("baseline clone" + " ".join(f"{x:7.2f}" for x in clone_base))
    print("baseline diff " + " ".join(f"{x:7.2f}" for x in (clone_base - ref_base)))
    print("coh ref      " + " ".join(f"{x:7.2f}" for x in ref_coh))
    print("coh clone    " + " ".join(f"{x:7.2f}" for x in clone_coh))

    ok = True
    limit_rms_4k = 0.35 if level == "-60" else 0.10
    limit_max_4k = 0.50 if level == "-60" else 0.20
    label = "CRUNCH" if level == "-60" else "DRIVE"
    for tag in tags:
        ref, ref_coh = response(os.path.join(REF_DIR, f"drive_{tag}_{level}.wav"), dry)
        clone, clone_coh = response(os.path.join(CLONE_DIR, f"clone_drive_{tag}_{level}.wav"), dry)

        ref_delta = ref - ref_base
        clone_delta = clone - clone_base
        error = clone_delta - ref_delta
        coherent = (ref_coh >= 0.9) & (clone_coh >= 0.9)
        error = np.where(coherent, error, np.nan)

        below_4k = coherent & (FREQS <= 4000)
        valid = np.isfinite(error)
        rms_all = np.sqrt(np.nanmean(error ** 2))
        max_all = np.nanmax(np.abs(error))
        rms_4k = np.sqrt(np.nanmean(error[below_4k] ** 2))
        max_4k = np.nanmax(np.abs(error[below_4k]))

        print(f"\n[{tag}] ref delta  " + " ".join(f"{x:7.2f}" for x in ref_delta))
        print(f"[{tag}] clone delta" + " ".join(f"{x:7.2f}" for x in clone_delta))
        print(f"[{tag}] error      " + " ".join(f"{x:7.2f}" for x in error))
        print(f"[{tag}] RMS <=4kHz={rms_4k:.3f} dB, max <=4kHz={max_4k:.3f} dB, "
              f"RMS full={rms_all:.3f} dB, max full={max_all:.3f} dB, "
              f"coherent={int(valid.sum())}/{len(valid)}")

        passed = (np.all(valid)
                  and rms_4k <= limit_rms_4k
                  and max_4k <= limit_max_4k)
        print(f"[{tag}] {label} {'PASS' if passed else 'FAIL'} "
              f"(limits: RMS <= {limit_rms_4k:.2f} dB, max <= {limit_max_4k:.2f} dB)")

        if not passed:
            ok = False

    return ok


def main():
    ok_60 = compare_series(
        "-60",
        ["c125_min", "c375_min", "c625_min", "c875_min"],
    )
    ok_90 = compare_series(
        "-90",
        ["cmin_mid", "cmin_max"],
    )
    return 0 if ok_60 and ok_90 else 1


if __name__ == "__main__":
    raise SystemExit(main())
