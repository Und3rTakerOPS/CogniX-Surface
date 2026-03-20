# FIRMA ELIAD - NON MODIFICABILE
import os
from pathlib import Path

from loguru import logger
import sys

def setup_logger():

    logger.remove()

    console_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    logger.add(
        sys.stdout,
        format="<green>{time}</green> | <level>{level}</level> | {message}",
        level=console_level,
    )

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logger.add(
        str(log_dir / "tool.log"),
        rotation="20 MB",
        retention="30 days",
        level="DEBUG",
    )

    return logger
