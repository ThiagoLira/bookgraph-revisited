import logging
import sys
from pathlib import Path
from datetime import datetime

def setup_logging(output_dir: Path, verbose: bool = False) -> Path:
    """
    Sets up logging to console and a timestamped file in the output directory.
    Returns the path to the log file.
    """
    # Create output directory if not exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate log filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = output_dir / f"pipeline_run_{timestamp}.log"
    
    # Define format
    # "Clean and informative"
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_format = logging.Formatter(
        "%(levelname)s: %(message)s"
    )

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO if not verbose else logging.DEBUG)
    
    # Clear existing handlers
    root_logger.handlers = []
    
    # File Handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)
    
    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO if not verbose else logging.DEBUG)
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)
    
    # Silence some noisy libraries unless verbose
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("pyppeteer").setLevel(logging.WARNING)

    logging.info(f"Logging initialized. Writing logs to {log_file}")
    
    return log_file
