import argparse
import json
import sys
from pathlib import Path

from core.orchestrator import BuildOrchestrator, BuildOrchestratorError
from core.path_utils import resolve_from_project

def _available_profiles(config_root: Path, category: str):
    category_dir = config_root / category
    if not category_dir.exists() or not category_dir.is_dir():
        return []
    return sorted([p.stem for p in category_dir.glob("*.json")])

def _parse_list_arg(arg_value):
    if not arg_value:
        return []
    items = []
    if isinstance(arg_value, list):
        for val in arg_value:
            items.extend([x.strip() for x in val.split(",") if x.strip()])
    elif isinstance(arg_value, str):
        items.extend([x.strip() for x in arg_value.split(",") if x.strip()])
    return items

def main():
    default_config_path = resolve_from_project("configs/global_build.json")

    parser = argparse.ArgumentParser(
        description="Gentoo-Builder: Modular Gentoo Linux ISO & Image Builder",
        epilog="Use --help to see available arguments."
    )

    parser.add_argument(
        "architecture",
        nargs="?",
        default="x86_64",
        help="Target architecture (e.g. x86_64). Default: x86_64",
    )

    parser.add_argument(
        "-c", "--config",
        type=str,
        default=str(default_config_path),
        help="Path to global configuration JSON file.",
    )

    parser.add_argument(
        "--mode",
        choices=["mock", "real"],
        default="mock",
        help="Execution mode: 'mock' (simulation) or 'real' (chroot/build). Default: mock",
    )

    clean_group = parser.add_mutually_exclusive_group()
    clean_group.add_argument(
        "--clean", dest="clean", action="store_true", help="Clean previous build artifacts."
    )
    clean_group.add_argument(
        "--no-clean", dest="clean", action="store_false", help="Reuse previous build tree without pre-build cleanup."
    )
    parser.set_defaults(clean=False)

    parser.add_argument(
        "--force-isolated-toolchain",
        action="store_true",
        help="Force isolated Gentoo build_host toolchain in real mode, even if host tools are available."
    )

    parser.add_argument(
        "--target",
        choices=["livecd-stage1", "livecd-stage2", "diskimage-stage1", "diskimage-stage2", "netboot", "embedded"],
        default="livecd-stage2",
        help="Build target/type: 'livecd-stage1', 'livecd-stage2' (default), 'diskimage-stage1', 'diskimage-stage2', 'netboot', 'embedded'."
    )

    parser.add_argument("--init", type=str, default="openrc", help="Init system profile (openrc, systemd, runit, s6). Default: openrc")
    parser.add_argument("--desktop", type=str, help="Desktop environment profile (e.g. xfce, gnome)")
    parser.add_argument("--kernel", type=str, help="Kernel profile (e.g. gentoo-kernel-bin)")
    parser.add_argument("--bootloader", type=str, help="Bootloader profile (e.g. grub-uefi)")
    parser.add_argument("--packages", "--package", nargs="+", action="append", help="Package profiles to include (comma or space separated, or repeated)")
    parser.add_argument("--services", "--service", nargs="+", action="append", help="Service profiles to enable (comma or space separated, or repeated)")
    parser.add_argument("-o", "--output", type=str, help="Custom output filename")
    parser.add_argument("--list-options", action="store_true", help="List all available profiles")

    args = parser.parse_args()

    config_root = resolve_from_project("configs")

    if args.list_options:
        print("Available Gentoo-Builder Profiles:")
        for category in ["architectures", "inits", "desktops", "kernels", "bootloaders", "packages", "services", "live-users"]:
            profs = _available_profiles(config_root, category)
            print(f"  {category:<15}: {', '.join(profs) if profs else 'None'}")
        sys.exit(0)

    # Flatten nested list from action="append" + nargs="+"
    raw_pkgs = [item for sublist in args.packages for item in sublist] if args.packages else []
    raw_srvs = [item for sublist in args.services for item in sublist] if args.services else []

    try:
        orchestrator = BuildOrchestrator(
            arch=args.architecture,
            config_path=args.config,
            mode=args.mode,
            clean=args.clean,
            init_system=args.init,
            desktop=args.desktop,
            kernel=args.kernel,
            bootloader=args.bootloader,
            package_profiles=_parse_list_arg(raw_pkgs),
            service_profiles=_parse_list_arg(raw_srvs),
            output_name=args.output,
            force_isolated_toolchain=args.force_isolated_toolchain,
            target=args.target
        )
        orchestrator.build()
    except BuildOrchestratorError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
