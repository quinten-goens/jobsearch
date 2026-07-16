"""Shared paths and HTTP settings."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA = ROOT / "data"
CACHE = DATA / "cache"
DATA.mkdir(exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

WORKBOOK = ROOT / "conv" / "Sarah_Pernet_Brussels_Job_Search.xlsx"
ORGS_JSON = DATA / "orgs.json"
JOBS_JSON = DATA / "jobs.json"

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "").strip()

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9,fr;q=0.8,nl;q=0.7",
}
TIMEOUT = 20
