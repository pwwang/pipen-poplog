"""Populate logs from stdout/stderr to pipen runnning logs"""

from __future__ import annotations
from typing import TYPE_CHECKING

import re
import logging
from pathlib import Path
from contextlib import suppress
from yunpath import AnyPath, CloudPath
from pipen.pluginmgr import plugin
from pipen.utils import get_logger

if TYPE_CHECKING:
    from pipen import Pipen, Proc
    from pipen.job import Job

__version__ = "0.3.6"
PATTERN = r"\[PIPEN-POPLOG\]\[(?P<level>\w+?)\] (?P<message>.*)"
logger = get_logger("poplog")
levels = {"warn": "warning"}


class Singleton(type):
    """
    A metaclass for implementing the Singleton design pattern.

    The Singleton pattern ensures that a class has only one instance and provides
    a global point of access to that instance. This is achieved by overriding the
    `__call__` method of the metaclass to control the instantiation process.

    Attributes:
        _instances (dict): A dictionary to store the single instance of each class
            that uses this metaclass.

    Methods:
        __call__(cls, *args, **kwargs):
            Overrides the default behavior of creating a new instance. If an
            instance of the class already exists, it returns the existing instance.
            Otherwise, it creates a new instance, stores it in the `_instances`
            dictionary, and returns it.
    """

    _instances: dict[type, object] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class LogsPopulator:
    """
    A class to handle the population of logs from a given file-like object.

    Attributes:
        logfile (str | Path | CloudPath):
            The path to the log file. Can be a string, Path, or CloudPath object.
        handler (file-like object | None):
            The file handler used to read the log file. Initialized as None.
        residue (str):
            Residual content from the last read operation that was not a complete line.
        counter (int):
            A counter to track the number of times the `populate` method is called.
        max (int):
            The maximum number of log lines to read. A value of 0 means no limit.
        hit_message (str):
            A message to log when the maximum number of log lines has been reached.
        _max_hit (bool):
            A flag indicating whether the maximum number of log lines has been reached.

    Methods:
        increment_counter(n: int = 1) -> None:
            Increments the counter by a specified value (default is 1).
        max_hit() -> bool:
            Returns True if the maximum number of log lines has been reached,
            otherwise False.
        populate() -> list[str]:
            Reads the log file, processes its content, and returns a list of
            complete lines.
            Any incomplete line at the end of the file is stored as residue for the
            next read.
    """

    __slots__ = (
        "logfile",
        "handler",
        "residue",
        "counter",
        "max",
        "hit_message",
        "_max_hit",
    )

    def __init__(
        self,
        logfile: str | Path | CloudPath | None = None,
        max: int = 0,
        hit_message: str = "max messages reached",
    ) -> None:
        self.logfile = AnyPath(logfile) if isinstance(logfile, str) else logfile
        self.handler = None
        self.residue = ""
        self.counter = 0
        self.max = max
        self.hit_message = hit_message
        self._max_hit = False

    def increment_counter(self, n: int = 1) -> None:
        self.counter += n

    def max_hit(self) -> bool:
        return self._max_hit

    def populate(self) -> list[str]:
        if self._max_hit:
            return []

        if self.counter >= self.max > 0:
            self._max_hit = True
            return [self.hit_message]

        if not self.logfile.exists():  # type: ignore
            return []

        if isinstance(self.logfile, CloudPath):
            self.logfile._refresh_cache()

        if not self.handler:
            self.handler = self.logfile.open()  # type: ignore

        self.handler.flush()
        content = self.residue + self.handler.read()
        has_residue = content.endswith("\n")
        lines = content.splitlines()

        if has_residue or not lines:
            self.residue = ""
        else:
            self.residue = lines.pop(-1)

        return lines

    def __del__(self):
        if self.handler:
            with suppress(Exception):
                self.handler.close()


class PipenPoplogPlugin(metaclass=Singleton):
    """Populate logs from stdout/stderr to pipen runnning logs"""

    name = "poplog"
    priority = -9  # wrap command before runinfo plugin

    __version__: str = __version__
    __slots__ = ("populators",)

    def __init__(self) -> None:
        self.populators: dict[int, LogsPopulator] = {}

    @plugin.impl
    async def on_init(self, pipen: Pipen):
        """Initialize the options"""
        # default options
        pipen.config.plugin_opts.setdefault("poplog_loglevel", "info")
        pipen.config.plugin_opts.setdefault("poplog_pattern", PATTERN)
        pipen.config.plugin_opts.setdefault("poplog_jobs", [0])
        pipen.config.plugin_opts.setdefault("poplog_source", "stdout")
        pipen.config.plugin_opts.setdefault("poplog_max", 0)

    @plugin.impl
    async def on_start(self, pipen: Pipen):
        """Set the log level"""
        logger.setLevel(pipen.config.plugin_opts.poplog_loglevel.upper())

    @plugin.impl
    async def on_job_started(self, job: Job):
        """Initialize the populator for the job"""
        if job.index not in job.proc.plugin_opts.get("poplog_jobs", [0]):
            return

        if job.proc.plugin_opts.poplog_source == "stdout":
            logfile = job.stdout_file
        else:
            logfile = job.stderr_file

        if job.index not in self.populators:
            poplog_max = job.proc.plugin_opts.get("poplog_max", 0)
            self.populators[job.index] = LogsPopulator(
                logfile,  # type: ignore
                max=poplog_max,
                hit_message=(
                    f"Max messages reached ({poplog_max}), "
                    "check stdout/stderr files for more."
                ),
            )

    @plugin.impl
    async def on_job_polling(self, job: Job, counter: int):
        """Poll the job's stdout/stderr file and populate the logs"""
        if job.index not in self.populators:
            return

        proc = job.proc
        populator = self.populators[job.index]

        poplog_pattern = proc.plugin_opts.get("poplog_pattern", PATTERN)
        poplog_pattern = re.compile(poplog_pattern)

        lines = populator.populate()

        for line in lines:
            if populator.max_hit():
                job.log("warning", line, limit_indicator=False, logger=logger)
                break

            match = poplog_pattern.match(line)
            if not match:
                continue
            level = match.group("level").lower()
            level = levels.get(level, level)
            msg = match.group("message").rstrip()
            job.log(level, msg, limit_indicator=False, logger=logger)

            # count only when level is larger than poplog_loglevel
            levelno = logging._nameToLevel.get(level.upper(), 0)
            if not isinstance(levelno, int) or levelno >= logger.getEffectiveLevel():
                populator.increment_counter()

    @plugin.impl
    async def on_job_succeeded(self, job: Job):
        await self.on_job_polling.impl(self, job, 0)

    @plugin.impl
    async def on_job_failed(self, job: Job):
        with suppress(FileNotFoundError):
            await self.on_job_polling.impl(self, job, 0)

    @plugin.impl
    async def on_proc_done(self, proc: Proc, succeeded: bool | str):
        """Clear the populators after the proc is done"""
        for populator in self.populators.values():
            del populator
        self.populators.clear()

    @plugin.impl
    def on_jobcmd_prep(self, job: Job) -> str:
        # let the script flush each newline
        return '# by pipen_poplog\ncmd="stdbuf -oL $cmd"'


poplog_plugin = PipenPoplogPlugin()
