"""_pyluogu - 内嵌的 pyLuogu (用于 luogu-toolkit)

本模块是 pyLuogu (上游: https://github.com/NekoOS-Group/luogu-api-python)
的 vendored 副本, 重命名以避免命名冲突并能跟随 luogu-toolkit 一起打包。
所有源码版权归原作者所有, 详见本目录下的 NOTICE 文件。

为了减少噪音, 默认把 logger 关到 ERROR 级别 (原版是 WARNING)。
需要调试时手动调 `set_log_level("DEBUG")`。
"""
import logging
import typing

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[97m',  # White
        'INFO': '\033[94m',   # Blue
        'WARNING': '\033[93m',  # Orange
        'ERROR': '\033[91m',  # Red
        'CRITICAL': '\033[91m'  # Red
    }
    RESET = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.msg = f"{log_color}{record.msg}{self.RESET}"
        return super().format(record)

logger = logging.getLogger("LuoguAPI")
logger.setLevel(logging.ERROR)  # luogu-toolkit 默认静默
# 不自动 add console_handler (避免污染用户日志)
# 用户要调试时自己 setup

def set_log_level(level: typing.Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]):
    level_dict = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    logger.setLevel(level_dict.get(level, logging.ERROR))

from .api import luoguAPI
from .async_api import asyncLuoguAPI
from .static_api import staticLuoguAPI, luogu
from .types import *