import os
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional, List
from core.logger_setup import setup_logger

logger = setup_logger("toolchain_manager")

class ToolchainManagerError(Exception):
    pass

class ToolchainManager:
    """
    Gerencia um chroot secundário isolado (build_host), contendo todas as
    ferramentas de compilação e criação de imagem (emerge, mksquashfs, grub-mkrescue, xorriso).
    Isso garante que o projeto seja 100% agnóstico da distribuição host.
    """

    def __init__(
        self,
        workdir: Path,
        mode: str = "mock",
        force_isolated: bool = False,
        stage3_config: Optional[Dict[str, Any]] = None
    ):
        self.workdir = Path(workdir).resolve()
        self.mode = mode.lower()
        self.force_isolated = force_isolated
        self.stage3_config = stage3_config or {}
        
        self.build_host_dir = self.workdir / "build_host"
        self.cache_dir = self.workdir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.is_mounted = False

    def check_host_tools(self) -> bool:
        """Verifica se as ferramentas primárias de empacotamento de ISO existem no host."""
        required_tools = ["mksquashfs", "grub-mkrescue", "xorriso"]
        missing = [tool for tool in required_tools if shutil.which(tool) is None]
        if missing:
            logger.info(f"Ferramentas ausentes no host: {', '.join(missing)}")
            return False
        return True

    def _resolve_latest_stage3_url(self) -> str:
        txt_url = "https://distfiles.gentoo.org/releases/amd64/autobuilds/latest-stage3-amd64-openrc.txt"
        try:
            req = urllib.request.Request(txt_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                content = resp.read().decode("utf-8")
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-----") and "stage3-amd64-openrc" in line:
                        rel_path = line.split()[0]
                        full_url = f"https://distfiles.gentoo.org/releases/amd64/autobuilds/{rel_path}"
                        logger.info(f"Resolved latest build_host Stage3 URL: {full_url}")
                        return full_url
        except Exception as e:
            logger.warning(f"Could not resolve dynamic build_host stage3 URL: {e}")

        return "https://distfiles.gentoo.org/releases/amd64/autobuilds/20260719T170103Z/stage3-amd64-openrc-20260719T170103Z.tar.xz"

    def bootstrap_build_host(self):
        """Prepara o ambiente isolado build_host extraindo um Stage3 dedicado."""
        logger.info(f"Inicializando o ambiente de compilação isolado (build_host) em: {self.build_host_dir}")

        if self.mode == "mock":
            logger.info("[MOCK TOOLCHAIN] Criando estrutura mock para build_host")
            self.build_host_dir.mkdir(parents=True, exist_ok=True)
            (self.build_host_dir / "usr" / "bin").mkdir(parents=True, exist_ok=True)
            return

        if self.build_host_dir.exists() and (self.build_host_dir / "bin").exists():
            logger.info("Ambiente build_host já existente.")
            return

        url = self._resolve_latest_stage3_url()
        tarball_path = self.cache_dir / "stage3-build-host.tar.xz"

        if not tarball_path.exists():
            logger.info(f"Descarregando Stage3 para o build_host de {url}...")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req) as response, open(tarball_path, "wb") as out_file:
                    shutil.copyfileobj(response, out_file)
            except Exception as e:
                raise ToolchainManagerError(f"Falha no download do Stage3 do build_host: {e}")

        logger.info(f"Extraindo Stage3 isolado no build_host ({self.build_host_dir})...")
        self.build_host_dir.mkdir(parents=True, exist_ok=True)
        res = subprocess.run(["tar", "xpf", str(tarball_path), "-C", str(self.build_host_dir), "--numeric-owner"], capture_output=True, text=True)
        if res.returncode != 0:
            raise ToolchainManagerError(f"Falha ao extrair Stage3 do build_host: {res.stderr}")

        host_resolv = Path("/etc/resolv.conf")
        if host_resolv.exists():
            shutil.copy2(host_resolv, self.build_host_dir / "etc" / "resolv.conf")

    def mount_virtual_fs(self):
        if self.mode == "mock":
            logger.info(f"[MOCK TOOLCHAIN] Montando sistemas de arquivos virtuais no build_host")
            self.is_mounted = True
            return

        if os.geteuid() != 0:
            raise ToolchainManagerError("Privilégios de root necessários para montar o build_host.")

        logger.info(f"Montando proc, sys, dev no build_host em {self.build_host_dir}")
        mounts = [
            ("proc", self.build_host_dir / "proc", "proc", None),
            ("sysfs", self.build_host_dir / "sys", "sysfs", None),
            ("udev", self.build_host_dir / "dev", "devtmpfs", None),
            ("devpts", self.build_host_dir / "dev" / "pts", "devpts", None),
            ("tmpfs", self.build_host_dir / "dev" / "shm", "tmpfs", None),
        ]

        for src, target, fstype, opts in mounts:
            target.mkdir(parents=True, exist_ok=True)
            cmd = ["mount", "-t", fstype]
            if opts:
                cmd.extend(["-o", opts])
            cmd.extend([src, str(target)])
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 and "already mounted" not in res.stderr:
                logger.warning(f"Aviso ao montar {target}: {res.stderr.strip()}")

        self.is_mounted = True

    def umount_virtual_fs(self):
        if self.mode == "mock":
            logger.info(f"[MOCK TOOLCHAIN] Desmontando sistemas de arquivos do build_host")
            self.is_mounted = False
            return

        if not self.is_mounted and os.geteuid() != 0:
            return

        logger.info(f"Desmontando sistemas de arquivos do build_host em {self.build_host_dir}")
        targets = [
            self.build_host_dir / "dev" / "shm",
            self.build_host_dir / "dev" / "pts",
            self.build_host_dir / "dev",
            self.build_host_dir / "sys",
            self.build_host_dir / "proc",
        ]

        for target in targets:
            if target.exists():
                subprocess.run(["umount", "-l", str(target)], capture_output=True)

        self.is_mounted = False

    def run_in_build_host(self, command: List[str] | str) -> subprocess.CompletedProcess:
        if isinstance(command, str):
            cmd_args = ["/bin/sh", "-c", command]
            cmd_str = command
        else:
            cmd_args = command
            cmd_str = " ".join(command)

        if self.mode == "mock":
            logger.info(f"[MOCK BUILD_HOST CHROOT] Execute: {cmd_str}")
            return subprocess.CompletedProcess(args=cmd_args, returncode=0, stdout="[MOCK TOOLCHAIN OUTPUT]", stderr="")

        if os.geteuid() != 0:
            raise ToolchainManagerError("Execução no build_host chroot requer privilégios de root.")

        full_cmd = ["chroot", str(self.build_host_dir)] + cmd_args
        logger.info(f"[BUILD_HOST CHROOT] Execute: {cmd_str}")
        return subprocess.run(full_cmd, capture_output=True, text=True)
