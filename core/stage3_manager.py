import urllib.request
import subprocess
import shutil
import re
import os
from pathlib import Path
from typing import Dict, Any
from core.logger_setup import setup_logger

logger = setup_logger("stage3_manager")

class Stage3ManagerError(Exception):
    pass

class Stage3Manager:
    def __init__(self, workdir: Path, stage3_config: Dict[str, Any], mode: str = "mock"):
        self.workdir = Path(workdir).resolve()
        self.config = stage3_config
        self.mode = mode.lower()
        self.cache_dir = self.workdir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_latest_stage3_url(self, base_url: str) -> str:
        if base_url.endswith(".txt"):
            txt_url = base_url
        else:
            return base_url

        pattern = self.config.get("pattern", "stage3-amd64")
        try:
            req = urllib.request.Request(txt_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                content = resp.read().decode("utf-8")
                base_path_url = txt_url.rsplit("/", 1)[0] + "/"
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-----") and pattern in line:
                        rel_path = line.split()[0]
                        full_url = f"{base_path_url}{rel_path}"
                        logger.info(f"Resolved latest Gentoo Stage3 URL: {full_url}")
                        return full_url
        except Exception as e:
            logger.warning(f"Could not resolve dynamic stage3 URL from {txt_url}: {e}")

        # Construct a sensible fallback based on the txt_url or pattern
        base_path_url = txt_url.rsplit("/", 1)[0] + "/" if "/" in txt_url else "https://distfiles.gentoo.org/releases/amd64/autobuilds/"
        return f"{base_path_url}current-{pattern}-openrc/{pattern}-openrc-latest.tar.xz"

    def fetch_and_extract(self, target_root: Path):
        configured_url = self.config.get("url", "https://distfiles.gentoo.org/releases/amd64/autobuilds/latest-stage3-amd64-openrc.txt")
        url = self._resolve_latest_stage3_url(configured_url)
        filename = url.split("/")[-1]
        tarball_path = self.cache_dir / filename

        if self.mode == "mock":
            logger.info(f"[MOCK STAGE3] Fetching stage3 from {url}")
            logger.info(f"[MOCK STAGE3] Extracting to {target_root}")
            target_root.mkdir(parents=True, exist_ok=True)
            (target_root / "etc").mkdir(parents=True, exist_ok=True)
            (target_root / "bin").mkdir(parents=True, exist_ok=True)
            return

        if not tarball_path.exists():
            logger.info(f"Downloading Gentoo Stage3 from {url}...")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req) as response, open(tarball_path, "wb") as out_file:
                    shutil.copyfileobj(response, out_file)
            except Exception as e:
                raise Stage3ManagerError(f"Failed to download Stage3: {e}")

        logger.info(f"Extracting Gentoo Stage3 into {target_root}...")
        target_root.mkdir(parents=True, exist_ok=True)

        if os.geteuid() != 0:
            raise Stage3ManagerError(
                "Real mode requires root privileges (root/sudo).\n"
                "Extracting Stage3 creates device nodes (/dev/null, /dev/console) via mknod.\n"
                "Please run the command with sudo:\n"
                "  sudo python3 cli.py x86_64 --mode real ..."
            )

        tar_cmd = ["tar", "xpf", str(tarball_path), "-C", str(target_root), "--numeric-owner", "--xattrs-include='*.*'"]
        res = subprocess.run(tar_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise Stage3ManagerError(f"Failed to extract Stage3 tarball: {res.stderr}")

        logger.info("Stage3 extracted successfully.")
