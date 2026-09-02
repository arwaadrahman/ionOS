"""Start the real Ion local API for the Rust full-loop seam test.

Real FastAPI, real SQLite at migration head 0007, real routes. Only the Google
endpoint is synthetic in the test that drives this.
"""

import os
import pathlib
import shutil
import sys

API_DIR = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_DIR))
sys.path.insert(0, str(API_DIR / "tests"))

import uvicorn  # noqa: E402
from calendar_write_fixtures import seed_writable_event  # noqa: E402

from ion_api.db import create_database_engine  # noqa: E402
from ion_api.main import create_app  # noqa: E402
from ion_api.migrations import upgrade_to_head  # noqa: E402
from ion_api.settings import Settings  # noqa: E402

data_dir = pathlib.Path(sys.argv[1])
shutil.rmtree(data_dir, ignore_errors=True)
data_dir.mkdir(parents=True)
settings = Settings(data_dir=data_dir)
upgrade_to_head(settings.database_path)
seed_writable_event(create_database_engine(settings.database_path))

port = int(os.environ["ION_API_PORT"])
uvicorn.run(create_app(settings), host="127.0.0.1", port=port, log_level="error")
