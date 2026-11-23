# zkteco
Desktop UI for extracting and organizing ZKTeco attendance logs.

## Setup and run (macOS)

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

In VS Code, run the **Attendance app (.venv)** launch configuration.
For **Run Python File**, use **Python: Select Interpreter** from the Command
Palette and select `.venv/bin/python`. An already selected interpreter may
override the workspace default. Restart the app after changing interpreters.

If the app reports that `pyzk` is missing, make sure it is running with the
same interpreter used to install dependencies. The package is named `pyzk`,
but its Python import is `from zk import ZK`.
