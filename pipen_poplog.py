"""Populate logs from stdout/stderr to pipen runnning logs"""
from __future__ import annotations
from typing import TYPE_CHECKING

import re
from pipen.pluginmgr import plugin
from pipen.utils import get_logger

if TYPE_CHECKING:
    from pipen import Pipen, Proc
    from pipen.job import Job

__version__ = "0.0.0"
PATTERN = r'\[PIPEN-POPLOG\]\[(?P<level>\w+?)\] (?P<message>.*)'
logger = get_logger("poplog")
levels = {"warn": "warning"}


class PipenPoplogPlugin:
    """Populate logs from stdout/stderr to pipen runnning logs"""
    name = "poplog"
    priority = -1
    __version__: str = __version__

    def __init__(self) -> None:
        self.handlers = {}
        self.residules = {}

    def _poplog(self, proc: Proc, job: Job, end: bool = False):
        if job.index not in proc.plugin_opts.poplog_jobs:
            return

        if proc.plugin_opts.poplog_source == "stdout":
            source = job.stdout_file
        else:
            source = job.stderr_file

        poplog_pattern = proc.plugin_opts.get("poplog_pattern", PATTERN)
        poplog_max = proc.plugin_opts.get("poplog_max", 99)
        poplog_pattern = re.compile(poplog_pattern)

        if job.index not in self.handlers:
            self.handlers[job.index] = open(source, "r")
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
            job.log(level, msg, limit=poplog_max, logger=logger)

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
    async def on_job_polling(self, proc: Proc, job: Job):
        if proc.plugin_opts.poplog_source == "stdout":
            source = job.stdout_file
        else:
            source = job.stderr_file

        if source.exists():
            self._poplog(proc, job)

    @plugin.impl
    async def on_job_succeeded(self, proc: Proc, job: Job):
        self._poplog(proc, job, end=True)

    @plugin.impl
    async def on_job_failed(self, proc: Proc, job: Job):
        self._poplog(proc, job, end=True)

    @plugin.impl
    async def on_proc_done(self, proc: Proc, succeeded: bool | str):
        for handler in self.handlers.values():
            try:
                handler.close()
            except Exception:
                pass
        self.handlers.clear()
        self.residules.clear()


poplog_plugin = PipenPoplogPlugin()
