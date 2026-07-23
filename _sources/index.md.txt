# Gentoo-Builder Documentation

Welcome to the official documentation for **Gentoo-Builder**, a modular and automated pipeline tool designed to build customized Gentoo Linux images, ISOs, netboot tarballs, and minimal rootfs archives.

Gentoo-Builder is designed to be highly configurable, host-agnostic, and fully compatible with Gentoo's official Catalyst architecture and target patterns.

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

* **Cross-Architecture Support**: Built-in configuration profiles for 15+ CPU architectures, including `x86_64`, `x86`, `arm64`, `riscv`, `ppc`, and `sparc`.
* **Flexible Init Systems**: Seamless support for `openrc`, `systemd`, `runit`, and `s6` system initialization profiles.
* **Modular Software Selection**: Select packages dynamically via structured JSON profiles (`office`, `browsers`, `chat`, `development`, `multimedia`, `gaming`, etc.).
* **Multiple Output Targets**: Support for `livecd-stage1`, `livecd-stage2` (ISO), `diskimage-stage1`, `diskimage-stage2` (raw `.img`), `netboot`, and `embedded`.
* **Host Agnostic Toolchain**: Uses an isolated chroot system toolchain for compilation, preventing pollution of the host operating system.
