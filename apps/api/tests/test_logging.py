import logging

from ion_api.logging import configure_logging


def test_logging_writes_only_to_the_configured_user_local_path(tmp_path):
    logger = logging.getLogger("ion")
    logger.handlers.clear()
    log_path = tmp_path / "logs" / "ion.log"

    configure_logging(log_path)
    logger.info("fixture operation complete")

    assert log_path.is_file()
    assert "fixture operation complete" in log_path.read_text()
    logger.handlers.clear()
