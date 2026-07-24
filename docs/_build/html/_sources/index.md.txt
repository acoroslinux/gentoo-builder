# Gentoo Modern Documentation

Welcome to the official documentation for **Gentoo Modern** (`gentoo-builder`), a modular, automated, and dynamic pipeline tool designed to build customized Gentoo Linux LiveCD ISOs, Disk Images, RootFS Tarballs, and Minimal archives.

Gentoo Modern is designed to be highly configurable, host-agnostic, and fully compatible with Gentoo's official Catalyst architecture and target patterns.

```{toctree}
:maxdepth: 2
:caption: Table of Contents

installation
usage
architecture
advanced
tutorials
api
```

## Core Features

* **Multi-Architecture Support**: Built-in configuration profiles for 20 CPU architectures, including `x86_64`, `x86`, `arm64`, `riscv64`, `ppc64le`, `loong`, `s390x`, and `sparc64`.
* **Multi-Init System Support**: Native support for `OpenRC`, `Systemd`, `Runit`, and `S6` init system profiles with multi-init `/etc/machine-id` compatibility.
* **Calamares Graphical Installer**: Pre-configured Calamares installer with offline SquashFS extraction and automatic GRUB EFI configuration.
* **Flexible CLI Argument Syntax**: Pass package and service profiles via comma-separated strings, space-separated lists, or repeated arguments (`--packages filesystems,network-tools` or `--package audio`).
* **Multiple Output Artifact Formats**: Generate bootable LiveCD ISOs (`--format iso`), raw disk images (`--format img`), or compressed rootfs tarballs (`--format tarball`).
* **Modular Software Selection**: Select packages dynamically via structured JSON profiles (`filesystems`, `network-tools`, `system-utils`, `browsers`, `office`, `multimedia`, `gaming`, etc.).
* **Host-Agnostic Isolated Toolchain**: Option to use an isolated build-host chroot system toolchain for compilation, preventing pollution of the host system.
