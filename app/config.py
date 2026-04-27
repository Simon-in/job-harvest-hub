from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_DIR = BASE_DIR / "db"
DB_PATH = DB_DIR / "getjobs.db"

BOSS_BASE_URL = "https://www.zhipin.com/web/geek/jobs"
