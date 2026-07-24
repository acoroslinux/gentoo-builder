# Comprehensive Usage & Configuration Guide

This page provides an in-depth reference for configuring, extending, and executing **Gentoo Modern ISO & System Builder**.

---

## 1. Command-Line Arguments Reference

Gentoo-Builder is controlled via the `cli.py` script. The available arguments are:

| Argument | Description | Default / Options |
| --- | --- | --- |
| `architecture` | Target architecture profile to load. | `x86_64` (options: `arm64`, `x86`, `riscv64`, `ppc64`, `loong`, etc.) |
| `-c`, `--config` | Path to the global build configuration file. | `configs/global_build.json` |
| `--mode` | Execution mode. Simulation (`mock`) or real compilation (`real`). | `mock` / `real` |
| `--format` | Output artifact format. | `iso` (Bootable ISO), `img` (Disk Image), `tarball` (`.tar.xz` rootfs tarball) |
| `--clean` / `--no-clean` | Clean previous build trees before running. Preserves download caches. | Default: `--no-clean` |
| `--force-isolated-toolchain` | Force compilation inside an isolated build-host chroot. | Flag (false by default) |
| `--target` | Build compilation type or target stage. | `livecd-stage2` (options: `livecd-stage1`, `livecd-stage2`, `diskimage-stage1`, `diskimage-stage2`, `netboot`, `embedded`) |
| `--init` | Init system profile to apply. | `openrc` (options: `systemd`, `runit`, `s6`) |
| `--desktop` | Desktop environment profile to load. | Optional (e.g. `xfce`, `gnome`, `kde`, `awesome`) |
| `--kernel` | Kernel profile to apply. | Optional (e.g. `gentoo-kernel-bin`, `gentoo-sources`) |
| `--bootloader` | Bootloader profile to apply. | Optional (e.g. `grub-uefi`, `syslinux`) |
| `--packages`, `--package`, `-p` | Package profiles to include. Supports comma-separated, space-separated, or repeated flags. | Optional (e.g. `filesystems,network-tools,system-utils`) |
| `--services`, `--service`, `-s` | Service profiles to enable. Supports comma-separated, space-separated, or repeated flags. | Optional (e.g. `NetworkManager,dbus`) |
| `-o`, `--output` | Customize the final package output filename. | Generates name based on init, desktop, and arch. |
| `--list-options` | Prints all available JSON config profiles and exits. | Flag |

---

## 2. Flexible Argument Syntax Examples

### Passing Package Profiles
All of the following invocations are valid and produce identical results:
```bash
# Comma-separated
python3 cli.py x86_64 --packages filesystems,network-tools,system-utils

# Space-separated
python3 cli.py x86_64 --packages filesystems network-tools system-utils

# Repeated flag (singular or plural alias)
python3 cli.py x86_64 --package filesystems --package network-tools --package system-utils
```

### Passing Service Profiles
```bash
python3 cli.py x86_64 --services NetworkManager,dbus --service bluetoothd
```

### Output Format Selection
```bash
# LiveCD Bootable ISO (Default)
python3 cli.py x86_64 --format iso

# Raw Disk Image (.img)
python3 cli.py x86_64 --format img

# Compressed RootFS Tarball (.tar.xz for WSL2 / LXC / Docker / Cloud)
python3 cli.py x86_64 --format tarball
```

---

## 3. Configuration Profiles Structure

Every aspect of the build is modular and defined inside structured JSON files within the `configs/` directory.

### Global Build Configuration (`configs/global_build.json`)
Defines the base distribution details, default user accounts, groups, and packages that apply to all targets:
```json
{
  "global": {
    "distro": "Gentoo Modern",
    "version": "rolling",
    "maintainer": "AçorOS Linux Team"
  },
  "stage3": {
    "url": "https://distfiles.gentoo.org/releases/amd64/autobuilds/latest-stage3-amd64-openrc.txt"
  },
  "make_conf": {
    "COMMON_FLAGS": "-O2 -pipe",
    "ACCEPT_LICENSE": "*",
    "VIDEO_CARDS": "amdgpu radeon radeonsi nouveau intel fbdev vesa",
    "INPUT_DEVICES": "libinput synaptics evdev"
  },
  "use_flags": [
    "unicode", "nls", "udev", "dbus", "opengl", "egl", "text", "python", "mount", "alsa", "libproxy", "dist-kernel"
  ],
  "packages": [
    "app-admin/sudo", "net-misc/dhcpcd", "net-misc/networkmanager", "sys-apps/util-linux"
  ],
  "services": ["dbus", "NetworkManager"],
  "live_user": {
    "username": "live",
    "password": "live",
    "groups": ["wheel", "audio", "video", "input", "plugdev"]
  }
}
```

### Architecture Configuration (`configs/architectures/*.json`)
Injects architecture-specific compiler flags (`CFLAGS`), `ACCEPT_KEYWORDS`, stage3 URLs, and default profile paths (e.g., `configs/architectures/arm64.json`):
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

---

## 4. Real Mode Execution Pipeline

When executing in `--mode real`:
1. **Stage3 Fetch & Verification**: Downloads and extracts the latest matching Gentoo Stage3 archive into `workdir/<arch>/chroot`.
2. **Chroot Initialization**: Binds `/proc`, `/sys`, `/dev`, and `/etc/resolv.conf`.
3. **Portage Sync & Autounmasking**: Executes `emerge-webrsync` and configures hardware-optimized `make.conf` (`MAKEOPTS`). Passes `--autounmask-write=y --autounmask-continue=y` to handle USE flag dependencies automatically.
4. **Package Compilation**: Runs `emerge` for base, desktop, and user package profiles.
5. **System Customization**:
   * Sets up `live` user and `root` passwords.
   * Generates `/etc/os-release`, `/etc/issue`, and `/etc/gentoo_modern-release`.
   * Configures multi-init `/etc/machine-id` file and DBus symlinks.
   * Enables services according to the init system (`OpenRC`, `Systemd`, `Runit`, `S6`).
6. **Artifact Generation**:
   * Compresses chroot into SquashFS (`/live/filesystem.squashfs`).
   * Configures GRUB EFI / Syslinux bootloaders.
   * Generates `.iso`, `.img`, or `.tar.xz` with MD5 and SHA256 checksum files.
