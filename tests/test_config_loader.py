import pytest
from core.config_loader import ConfigLoader

def test_load_global_config():
    loader = ConfigLoader()
    cfg = loader.assemble_build_config("configs/global_build.json", desktop="xfce", kernel="gentoo-kernel-bin")
    assert "app-admin/sudo" in cfg["packages"]
    assert "xfce-base/xfce4-meta" in cfg["packages"]
    assert "sys-kernel/gentoo-kernel-bin" in cfg["packages"]
    assert "X" in cfg["use_flags"]
