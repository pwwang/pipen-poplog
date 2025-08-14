"""Populate logs from stdout/stderr to pipen runnning logs"""
from __future__ import annotations
from typing import TYPE_CHECKING

import re
import logging
from yunpath import CloudPath
from pipen.pluginmgr import plugin
from pipen.utils import get_logger

if TYPE_CHECKING:
    from pipen import Pipen, Proc
    from pipen.job import Job

__version__ = "0.3.4"
PATTERN = r'\[PIPEN-POPLOG\]\[(?P<level>\w+?)\] (?P<message>.*)'
logger = get_logger("poplog")
levels = {"warn": "warning"}


class PipenPoplogPlugin:
    """Populate logs from stdout/stderr to pipen runnning logs"""
    name = "poplog"
    priority = -9  # wrap command before runinfo plugin

    __version__: str = __version__
    __slots__ = ("handlers", "residules", "count")

    def __init__(self) -> None:
        self.handlers = {}
        self.residules = {}
        self.count = 0

    def _stop_populating(self, poplog_max: int, job: Job, limit: int) -> bool:
        if self.count > poplog_max:
            return True

        if self.count == poplog_max:
            job.log(
                "warning",
                "Poplog reached max (%s), stop populating",
                poplog_max,
                limit=limit,
                limit_indicator=False,
                logger=logger,
            )
            self.count += 1
            return True
        return False

    def _poplog(self, job: Job, end: bool = False):
        proc = job.proc
        if job.index not in proc.plugin_opts.poplog_jobs:
            return

        poplog_max = proc.plugin_opts.get("poplog_max", 99)
        poplog_jobs = proc.plugin_opts.get("poplog_jobs", [0])

        limit = max(poplog_jobs) + 1
        if self._stop_populating(poplog_max, job, limit):
            return

        poplog_pattern = proc.plugin_opts.get("poplog_pattern", PATTERN)
        poplog_pattern = re.compile(poplog_pattern)

        if proc.plugin_opts.poplog_source == "stdout":
            source = job.stdout_file
        else:
            source = job.stderr_file

        if job.index not in self.handlers:
            self.handlers[job.index] = source.open()
            self.residules[job.index] = ""

        handler = self.handlers[job.index]
        handler.flush()
        residue = self.residules[job.index]
        content = residue + handler.read()
        has_residue = content.endswith("\n")
        lines = content.splitlines()

        if has_residue or not lines:
            self.residules[job.index] = ""
        else:
            self.residules[job.index] = lines.pop(-1)

        for line in lines:
            match = poplog_pattern.match(line)
            if not match:
                continue
            level = match.group("level").lower()
            level = levels.get(level, level)
            msg = match.group("message").rstrip()
            job.log(level, msg, limit=limit, limit_indicator=False, logger=logger)
            # count only when level is larger than poplog_loglevel
            levelno = logging.getLevelName(level.upper())
            if not isinstance(levelno, int) or levelno >= logger.getEffectiveLevel():
                self.count += 1

            if self._stop_populating(poplog_max, job, limit):
                return

    @plugin.impl
    async def on_init(self, pipen: Pipen):
        """Initialize the options"""
        # default options
        pipen.config.plugin_opts.poplog_loglevel = "info"
        pipen.config.plugin_opts.poplog_pattern = PATTERN
        pipen.config.plugin_opts.poplog_jobs = [0]
        pipen.config.plugin_opts.poplog_source = "stdout"
        pipen.config.plugin_opts.poplog_max = 99

    @plugin.impl
    async def on_start(self, pipen: Pipen):
        """Set the log level"""
        logger.setLevel(pipen.config.plugin_opts.poplog_loglevel.upper())

    @plugin.impl
    async def on_job_polling(self, job: Job, counter: int):
        """Poll the job's stdout/stderr file and populate the logs"""

        if job.proc.plugin_opts.poplog_source == "stdout":
            source = job.stdout_file
        else:
            source = job.stderr_file

        if isinstance(source, CloudPath):
            source._refresh_cache()

        if source.exists():
            self._poplog(job)

    @plugin.impl
    async def on_job_succeeded(self, job: Job):
        self._poplog(job, end=True)

    @plugin.impl
    async def on_job_failed(self, job: Job):
        try:
            self._poplog(job, end=True)
        except FileNotFoundError:
            # In case the file is not there
            pass

    @plugin.impl
    async def on_proc_done(self, proc: Proc, succeeded: bool | str):
        for handler in self.handlers.values():
            try:
                handler.close()
            except Exception:
                pass

        self.handlers.clear()
        self.residules.clear()
        self.count = 0

    @plugin.impl
    def on_jobcmd_prep(job: Job) -> str:
        # let the script flush each newline
        return '# by pipen_poplog\ncmd="stdbuf -oL $cmd"'


poplog_plugin = PipenPoplogPlugin()
