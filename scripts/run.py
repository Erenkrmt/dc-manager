#!/usr/bin/env python3
"""
Production entry point – runs Streamlit and FastAPI side-by-side.
Used by Docker; for local dev use `streamlit run` or `uvicorn` directly.
"""

import sys
import os
import subprocess
import signal
import time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    """Start Streamlit and FastAPI servers in parallel."""
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("run")

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Read ports from environment (with defaults)
    api_port = os.getenv("API_PORT", "8000")
    streamlit_port = os.getenv("STREAMLIT_PORT", "8501")

    # Start FastAPI server
    api_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.web.api:app", "--host", "0.0.0.0", "--port", api_port],
        cwd=project_root,
    )
    logger.info("FastAPI server started on port %s (PID %d)", api_port, api_process.pid)

    # Small delay to let API start before Streamlit tries to launch its thread
    time.sleep(1)

    # Start Streamlit
    streamlit_process = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", "src/web/app.py",
            "--server.port", streamlit_port,
            "--server.address", "0.0.0.0",
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ],
        cwd=project_root,
    )
    logger.info("Streamlit started on port %s (PID %d)", streamlit_port, streamlit_process.pid)

    # Forward signals to both processes
    def signal_handler(sig, _frame):
        logger.info("Shutting down...")
        api_process.terminate()
        streamlit_process.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Wait for either process to exit
    api_process.wait()
    streamlit_process.wait()


if __name__ == "__main__":
    main()