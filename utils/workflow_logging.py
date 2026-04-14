import logging
import sys
from langchain_core.messages import HumanMessage


def configure_application_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)


def get_application_logger(name: str) -> logging.Logger:
    configure_application_logging()
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def log_ai_request(
    logger: logging.Logger,
    *,
    request_id: str,
    model: str,
    prompt: str,
) -> None:
    logger.info("AI request request_id=%s model=%s", request_id, model)
    HumanMessage(content=prompt).pretty_print()
