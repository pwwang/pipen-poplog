"""Populate logs from stdout/stderr to pipen runnning logs"""

from __future__ import annotations
from typing import TYPE_CHECKING

import re
import logging
from pathlib import Path
from contextlib import suppress
from panpath import PanPath, CloudPath
from pipen.pluginmgr import plugin
from pipen.utils import get_logger

if TYPE_CHECKING:
    from pipen import Pipen, Proc
    from pipen.job import Job

__version__ = "1.1.2"
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
        max_hit -> bool:
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
        "_pos",
    )

    def __init__(
        self,
        logfile: str | Path | CloudPath | None = None,
        max: int = 0,
        hit_message: str = "max messages reached",
    ) -> None:
        self.logfile = PanPath(logfile) if isinstance(logfile, str) else logfile
        self.handler = None
        self.residue: str = ""
        self.counter = 0
        self.max = max
        self.hit_message = hit_message
        self._max_hit = False
        self._pos = 0

    def increment_counter(self, n: int = 1) -> None:
        self.counter += n

    @property
    def max_hit(self) -> bool:
        return self._max_hit

    async def populate(self) -> list[str]:
        if self._max_hit:
            return []

        if self.counter >= self.max > 0:
            self._max_hit = True
            return [self.hit_message]

        if not await self.logfile.a_exists():
            return []

        if not self.handler and not isinstance(self.logfile, CloudPath):
            self.handler = await self.logfile.a_open("r").__aenter__()

        if not isinstance(self.logfile, CloudPath):
            content: str = self.residue + await self.handler.read()
        else:
            async with self.logfile.a_open("r") as f:
                await f.seek(self._pos)
                content: str = self.residue + str(await f.read())
                self._pos = await f.tell()

        has_residue = content.endswith("\n")
        lines = content.splitlines()

        if has_residue or not lines:
            self.residue = ""
        else:
            self.residue = lines.pop(-1)

        return lines

    async def destroy(self) -> None:
        if self.handler and not isinstance(self.logfile, CloudPath):
            await self.handler.close()
            self.handler = None


class PipenPoplogPlugin(metaclass=Singleton):
    """Populate logs from stdout/stderr to pipen runnning logs"""

    name = "poplog"
    priority = -9  # wrap command before runinfo plugin

    __version__: str = __version__
    # flushing handlers: The handlers of the logger that need to be flushed
    # this is to ensure that the logs are written to the file and uploaded if
    # using cloud files for logging
    __slots__ = ("populators", "flushing_handlers")

    def __init__(self) -> None:
        self.populators: dict[int, LogsPopulator] = {}
        self.flushing_handlers: list[logging.Handler] = []

    def _clear_residues(self, job: Job) -> None:
        """Clear residues in all populators"""
        if job.index not in self.populators:
            return

        populator = self.populators[job.index]
        poplog_pattern = re.compile(job.proc.plugin_opts.get("poplog_pattern", PATTERN))

        if populator.residue:
            line = populator.residue
            populator.residue = ""

            if populator.max_hit:
                return

            match = poplog_pattern.match(line)
            if not match:
                return

            level = match.group("level").lower()
            level = levels.get(level, level)
            msg = match.group("message").rstrip()
            job.log(level, msg, limit_indicator=False, logger=logger)
            # self._flush_hanlders()

            # count only when level is larger than poplog_loglevel
            levelno = logging._nameToLevel.get(level.upper(), 0)
            base_logger = getattr(logger, "logger", logger)
            if (
                not isinstance(levelno, int)
                or levelno >= base_logger.getEffectiveLevel()
            ):
                populator.increment_counter()

    # async def _is_remote_filesystem(self, path: str) -> bool:
    #     """Check if a path is on a remote/network filesystem.

    #     Remote filesystems may require explicit flushing to ensure data is
    #     written promptly. This includes NFS, FUSE-based cloud storage (like
    #     GCS, S3), SMB/CIFS, and other network filesystems.

    #     Args:
    #         path: The file path to check

    #     Returns:
    #         True if the path is on a remote/network filesystem
    #     """
    #     ppath = PanPath(path)
    #     try:
    #         # Get the real path to handle symlinks
    #         real_path = await ppath.a_resolve()

    #         # Read /proc/mounts to find the filesystem type
    #         # This is Linux-specific but works in most environments
    #         async with PanPath('/proc/mounts').a_open('r') as f:
    #             mounts = await f.readlines()

    #         # Find the best matching mount point (longest match)
    #         best_match_fs = None
    #         best_match_len = 0

    #         for line in mounts:
    #             parts = line.split()
    #             if len(parts) < 3:
    #                 continue
    #             mount_point = parts[1]
    #             fs_type = parts[2]

    #             # Check if the path starts with this mount point
    #             if str(real_path).startswith(mount_point):
    #                 if len(mount_point) > best_match_len:
    #                     best_match_fs = fs_type
    #                     best_match_len = len(mount_point)

    #         if not best_match_fs:
    #             return False

    #         # List of filesystem types that are typically remote/network/cloud
    #         # and may need explicit flushing
    #         remote_fs_types = {
    #             'nfs', 'nfs4',  # NFS
    #             'cifs', 'smb', 'smbfs',  # SMB/CIFS
    #             'fuse', 'fuseblk', 'fusectl',  # FUSE (cloud storage)
    #             'gcs', 'gcsfuse',  # Google Cloud Storage
    #             's3fs', 's3',  # S3
    #             'afs',  # Andrew File System
    #             'coda',  # Coda distributed file system
    #             'ocfs2',  # Oracle Cluster File System
    #             'glusterfs',  # GlusterFS
    #             'lustre',  # Lustre
    #             'davfs',  # WebDAV
    #         }

    #         # Check exact match
    #         if best_match_fs in remote_fs_types:
    #             return True

    #         # Check if it's a FUSE variant (e.g., fuse.s3fs, fuse.gcsfuse)
    #         if best_match_fs.startswith('fuse.'):
    #             return True

    #         return False
    #     except Exception:
    #         # If we can't determine the filesystem type, be conservative
    #         # and assume it might be remote if it's under common mount points
    #         return path.startswith('/mnt') or path.startswith('/mount')

    # def _flush_hanlders(self):
    #     if not self.flushing_handlers:
    #         return

    #     for h in self.flushing_handlers:
    #         with suppress(Exception):
    #             h.stream.flush()
    #             os.fsync(h.stream.fileno())

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
        # # Find handlers to flush if they are file handlers from remote path
        # base_logger = getattr(logger, "logger", logger)
        # for h in getattr(base_logger, "handlers", []):
        #     stream = getattr(h, "stream", None)
        #     if (
        #         not stream
        #         or not hasattr(stream, "name")
        #         or not isinstance(stream.name, str)
        #         or not await self._is_remote_filesystem(stream.name)
        #     ):
        #         continue

        #     self.flushing_handlers.append(h)

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
                logfile,
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

        lines = await populator.populate()
        for line in lines:
            if populator.max_hit:
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

        # flush all handlers
        # self._flush_hanlders()

    @plugin.impl
    async def on_job_succeeded(self, job: Job):
        await self.on_job_polling(job, 0)
        self._clear_residues(job)

    @plugin.impl
    async def on_job_failed(self, job: Job):
        with suppress(FileNotFoundError, AttributeError):
            await self.on_job_polling(job, 0)
        self._clear_residues(job)

    @plugin.impl
    async def on_job_killed(self, job: Job):
        with suppress(FileNotFoundError, AttributeError):
            await self.on_job_polling(job, 0)
        self._clear_residues(job)

    @plugin.impl
    async def on_proc_done(self, proc: Proc, succeeded: bool | str):
        """Clear the populators after the proc is done"""
        for populator in self.populators.values():
            await populator.destroy()
        self.populators.clear()

    @plugin.impl
    def on_jobcmd_prep(self, job: Job) -> str:
        # let the script flush each newline
        return '# by pipen_poplog\ncmd="stdbuf -oL $cmd"'


poplog_plugin = PipenPoplogPlugin()
