import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.path_utils import resolve_from_project
from core.logger_setup import setup_logger

logger = setup_logger("config_loader")

class ConfigLoaderError(Exception):
    pass

class ConfigLoader:
    def __init__(self, config_root: Optional[Path] = None):
        self.config_root = config_root or resolve_from_project("configs")

    def load_json(self, relative_or_abs_path: str | Path) -> Dict[str, Any]:
        path = Path(relative_or_abs_path)
        if not path.is_absolute():
            candidate = resolve_from_project(path)
            if candidate.exists():
                path = candidate
            else:
                path = self.config_root / path

        if not path.exists():
            raise ConfigLoaderError(f"Configuration file not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise ConfigLoaderError(f"Error parsing JSON from {path}: {e}")

    def load_profile(self, category: str, profile_name: str) -> Dict[str, Any]:
        if not profile_name.endswith(".json"):
            profile_name = f"{profile_name}.json"
        path = self.config_root / category / profile_name
        return self.load_json(path)

    def assemble_build_config(
        self,
        global_config_path: str | Path,
        init_system: Optional[str] = "openrc",
        desktop: Optional[str] = None,
        kernel: Optional[str] = None,
        bootloader: Optional[str] = None,
        package_profiles: Optional[List[str]] = None,
        service_profiles: Optional[List[str]] = None,
        live_profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        base_cfg = self.load_json(global_config_path)
        merged = {
            "global": base_cfg.get("global", {}),
            "stage3": base_cfg.get("stage3", {}),
            "make_conf": base_cfg.get("make_conf", {}),
            "use_flags": base_cfg.get("use_flags", []),
            "packages": base_cfg.get("packages", []),
            "services": base_cfg.get("services", []),
            "kernel": {},
            "bootloader": {},
            "live_user": base_cfg.get("live_user", {}),
            "custom_files": base_cfg.get("custom_files", []),
            "init_system": "openrc"
        }

        # Apply Init system profile (openrc, systemd, runit, s6)
        if init_system:
            init_cfg = self.load_profile("inits", init_system)
            merged["init_system"] = init_cfg.get("init_system", init_system)
            if "stage3" in init_cfg:
                merged["stage3"].update(init_cfg["stage3"])
            merged["packages"].extend(init_cfg.get("packages", []))
            merged["use_flags"].extend(init_cfg.get("use_flags", []))

        # Apply base customizations if existing
        base_custom_path = self.config_root / "base_customizations.json"
        if base_custom_path.exists():
            base_custom = self.load_json(base_custom_path)
            merged["make_conf"].update(base_custom.get("make_conf", {}))
            merged["use_flags"].extend(base_custom.get("use_flags", []))

        # Desktop profile
        if desktop:
            d_cfg = self.load_profile("desktops", desktop)
            merged["packages"].extend(d_cfg.get("packages", []))
            merged["services"].extend(d_cfg.get("services", []))
            merged["use_flags"].extend(d_cfg.get("use_flags", []))
            merged["make_conf"].update(d_cfg.get("make_conf", {}))

        # Kernel profile
        if kernel:
            k_cfg = self.load_profile("kernels", kernel)
            merged["kernel"] = k_cfg
            merged["packages"].extend(k_cfg.get("packages", []))

        # Bootloader profile
        if bootloader:
            b_cfg = self.load_profile("bootloaders", bootloader)
            merged["bootloader"] = b_cfg

        # Package profiles
        for pkg_p in (package_profiles or []):
            p_cfg = self.load_profile("packages", pkg_p)
            merged["packages"].extend(p_cfg.get("packages", []))

        # Service profiles
        for srv_p in (service_profiles or []):
            s_cfg = self.load_profile("services", srv_p)
            merged["services"].extend(s_cfg.get("services", []))

        # Live user profile
        if live_profile:
            l_cfg = self.load_profile("live-users", live_profile)
            merged["live_user"].update(l_cfg)

        # Deduplicate packages and use flags
        merged["packages"] = sorted(list(set(merged["packages"])))
        merged["use_flags"] = sorted(list(set(merged["use_flags"])))
        merged["services"] = sorted(list(set(merged["services"])))

        return merged
