# -*- coding: utf-8 -*-
"""
Core logger configuration for the gentoo-builder project.
Provides color-coded console output and rotating file log capabilities.
"""

import logging
import sys
from pathlib import Path

COLOR_DEBUG = "\033[94m"    # Blue
COLOR_INFO = "\033[92m"     # Green
COLOR_WARNING = "\033[93m"  # Yellow
COLOR_ERROR = "\033[91m"    # Red
COLOR_CRITICAL = "\033[95m" # Magenta
COLOR_RESET = "\033[0m"

def supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

class ColorFormatter(logging.Formatter):
    level_colors = {
        logging.DEBUG: COLOR_DEBUG,
        logging.INFO: COLOR_INFO,
        logging.WARNING: COLOR_WARNING,
        logging.ERROR: COLOR_ERROR,
        logging.CRITICAL: COLOR_CRITICAL,
    }

    def format(self, record):
        message = super().format(record)
        if supports_color():
            colour = self.level_colors.get(record.levelno, COLOR_RESET)
            message = f"{colour}{message}{COLOR_RESET}"
        return message

def setup_logger(name: str = "gentoo_builder", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(
        ColorFormatter("%(asctime)s - [%(name)s] - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(console_handler)

    return logger
