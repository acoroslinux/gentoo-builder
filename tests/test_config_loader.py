import pytest
from core.config_loader import ConfigLoader

def test_load_global_config():
    loader = ConfigLoader()
    cfg = loader.assemble_build_config("configs/global_build.json", architecture="x86_64", init_system="systemd", desktop="xfce", kernel="gentoo-kernel-bin")
    assert "app-admin/sudo" in cfg["packages"]
    assert "sys-apps/systemd" in cfg["packages"]
    assert "xfce-base/xfce4-meta" in cfg["packages"]
    assert "sys-kernel/gentoo-kernel-bin" in cfg["packages"]
    assert "systemd" in cfg["use_flags"]
    assert "dracut" in cfg["use_flags"]
    assert cfg["make_conf"]["CFLAGS"] == "-O2 -pipe -march=x86-64"
    assert "amdgpu" in cfg["make_conf"]["VIDEO_CARDS"]
    assert "libinput" in cfg["make_conf"]["INPUT_DEVICES"]
    assert cfg["default_profile"] == "default/linux/amd64/23.0/split-usr"

def test_load_arm64_config():
    loader = ConfigLoader()
    cfg = loader.assemble_build_config("configs/global_build.json", architecture="arm64", init_system="openrc")
    assert cfg["make_conf"]["CFLAGS"] == "-O2 -pipe -march=armv8-a"
    assert cfg["make_conf"]["ACCEPT_KEYWORDS"] == "~arm64"
    assert cfg["default_profile"] == "default/linux/arm64/23.0/split-usr"
    assert "latest-stage3-arm64-openrc.txt" in cfg["stage3"]["url"]

def test_load_x86_config():
    loader = ConfigLoader()
    cfg = loader.assemble_build_config("configs/global_build.json", architecture="x86", init_system="systemd")
    assert cfg["make_conf"]["CFLAGS"] == "-O2 -pipe -march=i686"
    assert cfg["make_conf"]["ACCEPT_KEYWORDS"] == "~x86"
    assert cfg["default_profile"] == "default/linux/x86/23.0/split-usr"
    assert "latest-stage3-i686-systemd.txt" in cfg["stage3"]["url"]

def test_load_package_profiles():
    loader = ConfigLoader()
    cfg = loader.assemble_build_config(
        "configs/global_build.json",
        architecture="x86_64",
        init_system="openrc",
        package_profiles=["xorg", "wayland"]
    )
    assert "x11-base/xorg-server" in cfg["packages"]
    assert "dev-libs/wayland" in cfg["packages"]
    assert "x11-base/xwayland" in cfg["packages"]
    assert "X" in cfg["use_flags"]
    assert "wayland" in cfg["use_flags"]

