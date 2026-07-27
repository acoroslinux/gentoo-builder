#!/usr/bin/env python3
"""
Gentoo Modern Stage3 Seed Matrix Builder
Automates the creation of pristine Stage3 seed tarballs across target architectures
and init systems.

Usage:
  sudo python3 scripts/build_stage3_matrix.py --archs x86_64,arm64 --inits openrc,systemd
"""

import sys
import argparse
import subprocess
from pathlib import Path

DEFAULT_ARCHS = ["x86_64", "x86", "arm64", "arm", "riscv64"]
DEFAULT_INITS = ["openrc", "systemd"]
DEFAULT_DESKTOPS = ["base", "xfce"]

def main():
    parser = argparse.ArgumentParser(description="Build Gentoo Modern Stage3 Seed Tarballs Matrix")
    parser.add_argument("--archs", type=str, default="x86_64,arm64", help="Comma-separated target architectures")
    parser.add_argument("--inits", type=str, default="openrc,systemd", help="Comma-separated init systems")
    parser.add_argument("--desktops", type=str, default="base,xfce", help="Comma-separated desktop seeds ('base' or desktop profiles like 'xfce')")
    parser.add_argument("--output-dir", type=str, default="output/stage3_seeds", help="Directory to store generated stage3 seeds")
    parser.add_argument("--mode", type=str, choices=["mock", "real"], default="real", help="Build mode: 'mock' for dry-run, 'real' for compilation")
    parser.add_argument("--clean", action="store_true", help="Clean the workdir before building")

    args = parser.parse_args()

    arch_list = [a.strip() for a in args.archs.split(",") if a.strip()]
    init_list = [i.strip() for i in args.inits.split(",") if i.strip()]
    desktop_list = [d.strip() for d in args.desktops.split(",") if d.strip()]

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("🚀 GENTOO MODERN STAGE3 SEED MATRIX BUILDER")
    print("=" * 70)
    print(f"Architectures: {', '.join(arch_list)}")
    print(f"Init Systems:  {', '.join(init_list)}")
    print(f"Desktop Seeds: {', '.join(desktop_list)}")
    print(f"Output Path:   {output_dir}")
    print(f"Build Mode:    {args.mode}")
    print("=" * 70)

    total_builds = len(arch_list) * len(init_list) * len(desktop_list)
    current_build = 0

    for arch in arch_list:
        for init in init_list:
            for desktop in desktop_list:
                current_build += 1
                desktop_flag = [] if desktop == "base" else ["--desktop", desktop]
                out_name = f"gentoo-modern-stage3-{init}-{desktop}-{arch}.tar.xz"
                out_file = output_dir / out_name

                print(f"\n[BUILD {current_build}/{total_builds}] Generating Stage3 Seed: {out_name}")

                cmd = [
                    sys.executable, "cli.py", arch,
                    "--init", init,
                    "--format", "stage3",
                    "--kernel", "",
                    "--bootloader", "",
                    "--mode", args.mode,
                    "--clean",
                    "-o", str(out_file)
                ] + desktop_flag

                if args.mode == "real":
                    cmd.append("--force-isolated-toolchain")

                print(f"Executing: {' '.join(cmd)}")
                res = subprocess.run(cmd)
                if res.returncode != 0:
                    print(f"❌ Error: Build failed for {out_name} (exit code {res.returncode})", file=sys.stderr)
                    sys.exit(res.returncode)
                print(f"✅ Successfully built Stage3 Seed: {out_file}")

    print("\n" + "=" * 70)
    print(f"🎉 ALL {total_builds} STAGE3 SEED TARBALLS GENERATED SUCCESSFULLY!")
    print(f"Stored in: {output_dir}")
    print("=" * 70)

if __name__ == "__main__":
    main()
