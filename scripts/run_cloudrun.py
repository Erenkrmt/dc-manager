#!/usr/bin/env python3
"""
Cloud Run entry point – runs only the FastAPI server on $PORT.
Cloud Run sets the PORT environment variable automatically.
Designed for production with PostgreSQL via Cloud SQL.
"""

import os
import sys
import logging

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main() -> None:
    """Start FastAPI server on the Cloud Run assigned port."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("cloudrun")

    # Cloud Run injects PORT env var; default to 8080 if not set
    port = int(os.getenv("PORT", "8080"))
    logger.info("Starting FastAPI server on port %d", port)

    import uvicorn

    uvicorn.run(
        "src.web.api:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()