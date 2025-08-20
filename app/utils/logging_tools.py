import logging

def setup_logging(level: int = logging.INFO) -> None:
    """
    Setup logging configuration for the application.
    """
    fmt = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt)
