#!/usr/bin/env python3
"""Hello Cron - A simple script to demonstrate cron task execution with logging.

This script prints "Hello Cron" to the console and logs the event
using the project's logging system.
"""

import sys
from pathlib import Path

# Add backend to path to import logger
backend_path = Path(__file__).parent.parent / "backend" / "src"
sys.path.insert(0, str(backend_path))

try:
    from utils.logger import get_logger
    
    logger = get_logger(__name__)
except ImportError:
    # Fallback to standard logging if project logger is not available
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)


def main():
    """Main function to execute the cron task."""
    # Log task start
    logger.info("Cron task started", extra={"task": "hello_cron"})
    
    # Print to console
    print("Hello Cron")
    
    # Log successful execution
    logger.info(
        "Cron task completed successfully",
        extra={
            "task": "hello_cron",
            "output": "Hello Cron",
            "status": "success"
        }
    )


if __name__ == "__main__":
    main()
