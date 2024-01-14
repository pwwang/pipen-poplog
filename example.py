from pipen import Proc, Pipen


class PoplogDefault(Proc):
    """A default poplog proc"""
    input = "var:var"
    input_data = [0, 1, 2]
    script = """
      echo -n "[PIPEN-POPLOG][INFO] Log message "
      sleep 3  # Simulate message not read in time
      echo "by {{in.var}} 1"
      sleep 3
      echo "[PIPEN-POPLOG][ERROR] Log message by {{in.var}} 2"
      sleep 3
      echo "[PIPEN-POPLOG][INFO] Log message by {{in.var}} 3"
    """


class PoplogStderrLimitJobs(Proc):
    """A default poplog proc"""
    input = "var:var"
    input_data = [0, 1, 2]
    script = """
      echo -n "[POPLOG][INFO] Log message " >&2
      echo "by {{in.var}} 1" >&2
      echo "[POPLOG][DEBUG] Log message by {{in.var}} 2" >&2
      echo "[POPLOG][INFO] Log message by {{in.var}} 3" >&2
      echo "[POPLOG][INFO] Log message by {{in.var}} 4" >&2
      echo "[POPLOG][INFO] Log message by {{in.var}} 5" >&2
      echo "[POPLOG][INFO] Log message by {{in.var}} 6"
    """
    plugin_opts = {
        "poplog_jobs": [0, 1],
        "poplog_loglevel": "warning",
        "poplog_source": "stderr",
        "poplog_pattern": r'^\[POPLOG\]\[(?P<level>\w+?)\] (?P<message>.*)$',
        "poplog_max": 6,
    }


class PoplogError(Proc):
    """A default poplog proc"""
    input = "var:var"
    input_data = [0, 1, 2]
    script = """
      echo -n "[PIPEN-POPLOG][INFO] Log message "
      echo "by {{in.var}} 1"
      echo "[PIPEN-POPLOG][DEBUG] Log message by {{in.var}} 2"
      echo "[PIPEN-POPLOG][INFO] Log message by {{in.var}} 3"
      exit 1
    """


class Pipeline(Pipen):
    cache = False
    forks = 3
    starts = PoplogDefault, PoplogStderrLimitJobs, PoplogError


if __name__ == "__main__":
    Pipeline().run()
