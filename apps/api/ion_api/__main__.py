import sys

from ion_api.main import run
from ion_api.runtime import run_production

if sys.argv[1:] == ["--production"]:
    run_production()
else:
    run()
