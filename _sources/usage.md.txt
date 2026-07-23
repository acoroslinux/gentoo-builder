# Comprehensive Usage & Configuration Guide

This page provides an in-depth reference for configuring, extending, and executing Gentoo-Builder.

---

## 1. Command-Line Arguments Reference

Gentoo-Builder is controlled via the `cli.py` script. The available arguments are:

| Argument | Description | Default / Options |
| --- | --- | --- |
| `architecture` | Target architecture profile to load. | `x86_64` (options: `arm64`, `x86`, `riscv`, `ppc`, etc.) |
| `-c`, `--config` | Path to the global build configuration file. | `configs/global_build.json` |
| `--mode` | Execution mode. Simulation (`mock`) or real compilation (`real`). | `mock` / `real` |
| `--clean` / `--no-clean` | Clean previous build trees before running. Preserves download caches. | Default: `--no-clean` |
| `--force-isolated-toolchain` | Force compilation inside an isolated build-host chroot. | Flag (false by default) |
| `--target` | Build compilation type or target stage. | `livecd-stage2` (options below) |
| `--init` | Init system profile to apply. | `openrc` (options: `systemd`, `runit`, `s6`) |
| `--desktop` | Desktop environment profile to load. | Optional (e.g. `xfce`, `gnome`, `kde`, `awesome`) |
| `--kernel` | Kernel profile to apply. | Optional (e.g. `gentoo-kernel-bin`) |
| `--bootloader` | Bootloader profile to apply. | Optional (e.g. `grub-uefi`, `syslinux`) |
| `--packages` | Comma-separated list of on-demand package profiles. | Optional (e.g. `browsers,office,printing`) |
| `--services` | Comma-separated list of on-demand service profiles to start. | Optional (e.g. `printing-services,sharing-services`) |
| `-o`, `--output` | Customize the final package output filename. | Generates name based on init, desktop, and arch. |
| `--list-options` | Prints all available JSON config profiles and exits. | Flag |

---

## 2. Configuration Profiles Structure

Every aspect of the build is modular and defined inside structured JSON files within the `configs/` directory.

### Global Build Configuration (`configs/global_build.json`)
Defines the base distribution details, default user accounts, groups, and packages that apply to all targets:
```json
{
  "global": {
    "distro": "Gentoo Linux",
    "version": "rolling",
    "maintainer": "AçorOS Linux Team"
  },
  "stage3": {
    "url": "https://distfiles.gentoo.org/releases/amd64/autobuilds/latest-stage3-amd64-openrc.txt"
  },
  "make_conf": {
    "CFLAGS": "-O2 -pipe -march=x86-64",
    "ACCEPT_KEYWORDS": "~amd64",
    "ACCEPT_LICENSE": "*"
  },
  "use_flags": ["unicode", "nls", "udev", "dbus"],
  "packages": ["app-admin/sudo", "net-misc/dhcpcd"],
  "services": ["dbus"],
  "live_user": {
    "username": "live",
    "password": "live",
    "groups": ["wheel", "audio", "video"]
  }
}
```

### Architecture Configuration (`configs/architectures/*.json`)
Overrides variables like flags, keywords, stage3 URLs, and targets specific to the architecture (e.g., `configs/architectures/arm64.json`):
```json
{
  "make_conf": {
    "CFLAGS": "-O2 -pipe -march=armv8-a",
    "ACCEPT_KEYWORDS": "~arm64"
  },
  "stage3": {
    "url": "https://distfiles.gentoo.org/releases/arm64/autobuilds/latest-stage3-arm64-{init_system}.txt",
    "pattern": "stage3-arm64"
  },
  "default_profile": "default/linux/arm64/23.0/split-usr"
}
```

### Desktop Configuration (`configs/desktops/*.json`)
Defines graphical desktop environment configurations (e.g., packages, mouse settings, default configs):
```json
{
  "packages": [
    "xfce-base/xfce4-meta",
    "x11-themes/adwaita-icon-theme"
  ],
  "use_flags": [
    "gtk3",
    "xfce"
  ]
}
```

---

## 3. Real Mode Step-by-Step

To run a real Gentoo build:
1. Verify the configuration matches your expectations.
2. Run the script with root permissions:
   ```bash
   sudo python3 cli.py x86_64 --mode real --target livecd-stage2 --init openrc --desktop xfce --kernel gentoo-kernel-bin
   ```
3. Gentoo-Builder will execute:
   * **Stage3 Download**: Fetches the newest matching Gentoo stage3 from official mirrors.
   * **Chroot Setup**: Mounts `/proc`, `/sys`, `/dev` and copies resolv.conf.
   * **Emerge Synchronize**: Runs `emerge-webrsync` to update the ebuild tree.
   * **Compilation**: Runs `emerge` to compile and install all packages in parallel.
   * **Customization**: Creates the live user, enables services (e.g. `NetworkManager`, `cupsd`), and sets up keymaps.
   * **SquashFS Creation**: Compresses the chroot filesystem into a `filesystem.squashfs` file.
   * **Bootloader Config**: Generates GRUB, Systemd-boot, or Syslinux config.
   * **ISO Generation**: Packages everything into a bootable ISO with checksum files.
