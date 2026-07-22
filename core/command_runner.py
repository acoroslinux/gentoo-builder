import subprocess
import sys
import os
from typing import List, Optional, Dict, Tuple
from core.logger_setup import setup_logger

logger = setup_logger("command_runner")

class CommandRunner:
    @staticmethod
    def run_chroot_stream(
        chroot_path: str,
        command: List[str] | str,
        env: Optional[Dict[str, str]] = None,
        mode: str = "mock"
    ) -> subprocess.CompletedProcess:
        """
        Executa um comando em chroot fazendo STREAMING em tempo real de cada linha no console,
        para que o utilizador veja o avanço da compilação e não pense que o sistema travou.
        """
        if isinstance(command, str):
            cmd_str = command
            cmd_args = ["/bin/sh", "-c", command]
        else:
            cmd_str = " ".join(command)
            cmd_args = command

        if mode == "mock":
            print(f"\033[1m[MOCK CHROOT]\033[0m {cmd_str}")
            return subprocess.CompletedProcess(args=cmd_args, returncode=0, stdout="[MOCK OUTPUT]", stderr="")

        if os.geteuid() != 0:
            raise PermissionError("Real chroot execution requires root privileges.")

        full_cmd = ["chroot", str(chroot_path)] + cmd_args
        print(f"\033[1;34m[REAL CHROOT EXEC]\033[0m {cmd_str}")

        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        process = subprocess.Popen(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=full_env
        )

        stdout_lines = []
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            stdout_lines.append(line)

        process.wait()
        returncode = process.returncode
        stdout = "".join(stdout_lines)

        if returncode != 0:
            print(f"\033[91m[ERROR]\033[0m Command failed with exit code {returncode}")

        return subprocess.CompletedProcess(args=full_cmd, returncode=returncode, stdout=stdout, stderr="")
