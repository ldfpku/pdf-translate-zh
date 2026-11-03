# -*- coding: utf-8 -*-
"""Offline CUDA wheel-selection tests; no GPU or network required."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "pdf-translate-zh", "scripts")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True
import bootstrap  # noqa: E402

FAILS = []


def step(name, ok, detail=""):
    print(("  PASS " if ok else "  FAIL ") + name + ((" — " + detail) if detail else ""), flush=True)
    if not ok:
        FAILS.append(name)


def main():
    original_cfg = bootstrap.cfg
    bootstrap.cfg = lambda key, default="": ""
    available = ["cu134", "cu132", "cu130", "cu129", "cu128", "cu126", "cu124", "cu121", "cu118"]
    cases = [
        ({"cc": (12, 0), "cuda": (13, 4)}, ["cu134", "cu132", "cu130"]),
        ({"cc": (12, 0), "cuda": (12, 8)}, ["cu128"]),
        ({"cc": (12, 0), "cuda": (12, 6)}, ["cu126", "cu124", "cu121"]),
        ({"cc": (10, 0), "cuda": (13, 0)}, ["cu130", "cu129", "cu128"]),
        ({"cc": (8, 9), "cuda": (12, 4)}, ["cu124", "cu121", "cu118"]),
        ({"cc": (8, 6), "cuda": (13, 2)}, ["cu132", "cu130", "cu129"]),
        ({"cc": (7, 5), "cuda": (13, 4)}, ["cu134", "cu132", "cu130"]),
        ({"cc": (7, 0), "cuda": (13, 4)}, ["cu129", "cu128", "cu126"]),
        ({"cc": (6, 1), "cuda": (12, 8)}, ["cu126", "cu124", "cu121"]),
        ({"cuda": (12, 8)}, ["cu128", "cu126", "cu124"]),
        ({"cc": (8, 6)}, ["cu134", "cu132", "cu130"]),
        ({"cc": (12, 0), "cuda": (13, 4)}, ["cu128"]),
        ({"cc": (12, 0), "cuda": (14, 0)}, ["cu140", "cu136", "cu134"]),
        ({"cc": (13, 0), "cuda": (14, 0)}, ["cu140", "cu136", "cu134"]),
    ]
    try:
        for i, (info, expected) in enumerate(cases, 1):
            cand = ["cu128", "cu126", "cu124"] if i == 12 else (
                ["cu140", "cu136", *available] if i >= 13 else available)
            actual = bootstrap.cuda_tags(info, avail=cand)
            step("CUDA 候选规则 #%02d" % i, actual == expected,
                 "expected=%s actual=%s" % (expected, actual))
        bootstrap.cfg = lambda key, default="": "cu126" if key == "torch_cuda" else default
        pinned = bootstrap.cuda_tags({"cc": (12, 0), "cuda": (13, 4)}, avail=available)
        step("torch_cuda 配置置顶", pinned[0] == "cu126", str(pinned))
    finally:
        bootstrap.cfg = original_cfg
    print("\n结论：" + ("全部通过" if not FAILS else "失败：" + "、".join(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
