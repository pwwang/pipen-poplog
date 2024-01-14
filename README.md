# pipen-poplog

Populate logs from jobs to running log of the pipeline for [pipen][1].

## Installation

```bash
pip install -U pipen-poplog
```

## Enabling/Disabling the plugin

The plugin is registered via entrypoints. It's by default enabled. To disable it:
`plugins=[..., "no:log2file"]`, or uninstall this plugin.

## Usage

```python
from pipen import Proc, Pipen


class Poplog(Proc):
    input = "var:var"
    input_data = [0, 1, 2]
    script = """
        echo -n "[PIPEN-POPLOG][INFO] Log message "
        sleep 1  # Simulate message not read in time
        echo "by {{in.var}} 1"
        sleep 1
        echo "[PIPEN-POPLOG][ERROR] Log message by {{in.var}} 2"
        sleep 1
        echo "[PIPEN-POPLOG][INFO] Log message by {{in.var}} 3"
    """


if __name__ == "__main__":
    Pipen().run()
```

```
01-12 11:23:52 I core    ╭═══════════════ PoplogDefault ═════════════════╮
01-12 11:23:52 I core    ║ A default poplog proc                         ║
01-12 11:23:52 I core    ╰═══════════════════════════════════════════════╯
01-12 11:23:52 I core    PoplogDefault: Workdir: '.pipen/Pipeline/PoplogDefault'
01-12 11:23:52 I core    PoplogDefault: <<< [START]
01-12 11:23:52 I core    PoplogDefault: >>> [END]
01-12 11:23:56 I poplog  PoplogDefault: [0/2] Log message by 0 1
01-12 11:23:59 E poplog  PoplogDefault: [0/2] Log message by 0 2
01-12 11:24:02 I poplog  PoplogDefault: [0/2] Log message by 0 3
```

## Configuration

- `plugin_opts.poplog_loglevel`: The log level for poplog. Default: `info`.
- `plugin_opts.poplog_pattern`: The pattern to match the log message. Default: `r'\[PIPEN-POPLOG\]\[(?P<level>\w+)\] (?P<message>.*)'`.
- `plugin_opts.poplog_jobs`: The job indices to be populated. Default: `[0]` (the first job).
- `plugin_opts.poplog_max`: The total max number of the log message to be poplutated. Default: `99`.
- `plugin_opts.poplog_source`: The source of the log message. Default: `stdout`.


[1]: https://github.com/pwwang/pipen
