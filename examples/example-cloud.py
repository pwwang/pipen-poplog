from dotenv import load_dotenv
from pipen import Proc, run

load_dotenv()
BUCKET = "gs://handy-buffer-287000.appspot.com"


class TestLogsPopulator(Proc):

    input = "var"
    input_data = [1]
    output = "out:var:1"

    script = """
        echo [POPLOG][INFO] 1
        sleep 1
        echo [POPLOG][WARNING] 2
        sleep 1
        echo 3
        sleep 1
        echo [POPLOG][ERROR] 4
        sleep 1
        echo [POPLOG][CRITICAL] 5
    """


if __name__ == "__main__":
    run(
        "TestLogsPopulatorPipeline",
        TestLogsPopulator,
        cache=False,
        workdir=f"{BUCKET}/pipen-poplog-example",
        plugin_opts={
            "poplog_loglevel": "WARNING",
            "poplog_pattern": (
                r"^\[POPLOG\]\[(?P<level>INFO|WARNING|ERROR|CRITICAL)\] "
                r"(?P<message>.*)$"
            ),
        },
    )
