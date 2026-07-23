# Installation

This page guides you through setting up Gentoo-Builder on your local system.

## Prerequisites

The only strict requirement on the host operating system is Python 3.

### Python 3
Gentoo-Builder is built using Python 3 (3.8 or newer recommended).

### Isolated Chroot Toolchain (No Host Installation Needed)
Gentoo-Builder utilizes an isolated secondary chroot (`build_host`) containing all the necessary compilation and packaging utilities (such as `mksquashfs`, `grub-mkrescue`, `xorriso`, `parted`).

Therefore, **you do not need to install these tools on your host operating system**. 

If the builder detects that any of these utilities are missing on the host (or if the `--force-isolated-toolchain` flag is set), it will automatically bootstrap a dedicated Gentoo toolchain environment to perform the packaging tasks securely and cleanly, making the builder 100% distribution-agnostic. No software needs to be installed on your host system.

However, if your host operating system is Gentoo Linux and you prefer to build natively using host tools instead of the isolated chroot environment, you can optionally install the dependencies on your Gentoo host:

```bash
sudo emerge sys-fs/squashfs-tools sys-boot/grub dev-libs/libisoburn sys-block/parted
```

## Clone the Repository

Clone the project repository to your working environment:

```bash
git clone https://github.com/acoroslinux/gentoo-builder.git
cd gentoo-builder
```

## Virtual Environment (Optional)

It is highly recommended to run tests or manage helper scripts inside a Python virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt  # If requirements exist
```
