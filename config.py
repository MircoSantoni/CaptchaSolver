import os
from dotenv import load_dotenv

load_dotenv()

PLAYWRIGHT_USERNAME = os.getenv("PLAYWRIGHT_USERNAME")
PLAYWRIGHT_PASSWORD = os.getenv("PLAYWRIGHT_PASSWORD")
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"

PROXY_SERVER = os.getenv("PROXY_SERVER", None)
PROXY_USERNAME = os.getenv("PROXY_USERNAME", None)
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", None)

SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8080"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

