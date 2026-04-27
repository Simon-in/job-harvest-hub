from typing import Any


PLATFORM_OPTIONS: dict[str, dict[str, Any]] = {
    "boss": {
        "defaults": {"city_code": "101010100", "max_pages": 30},
        "city": [
            {"name": "北京", "code": "101010100"},
            {"name": "上海", "code": "101020100"},
            {"name": "广州", "code": "101280100"},
            {"name": "深圳", "code": "101280600"},
        ],
        "salary": [
            {"name": "不限", "code": "0"},
            {"name": "10K以下", "code": "402"},
            {"name": "10-20K", "code": "404"},
            {"name": "20-50K", "code": "406"},
        ],
        "fields": ["industry", "experience", "degree", "jobType"],
    },
    "liepin": {
        "defaults": {"city_code": "020", "max_pages": 30},
        "city": [
            {"name": "北京", "code": "010"},
            {"name": "上海", "code": "020"},
            {"name": "广州", "code": "050020"},
            {"name": "深圳", "code": "050090"},
        ],
        "salary": [
            {"name": "不限", "code": "0"},
            {"name": "10-20万", "code": "10$20"},
            {"name": "20-30万", "code": "20$30"},
            {"name": "30-50万", "code": "30$50"},
        ],
        "fields": ["city", "dq", "salary"],
    },
    "zhilian": {
        "defaults": {"city_code": "530", "max_pages": 30},
        "city": [
            {"name": "北京", "code": "530"},
            {"name": "上海", "code": "538"},
            {"name": "广州", "code": "763"},
            {"name": "深圳", "code": "765"},
        ],
        "salary": [
            {"name": "不限", "code": "0"},
            {"name": "6K-10K", "code": "6000,10000"},
            {"name": "10K-20K", "code": "10000,20000"},
            {"name": "20K以上", "code": "20000,*"},
        ],
        "fields": ["jl", "sl", "p"],
    },
}


def get_platform_options(platform: str) -> dict[str, Any] | None:
    return PLATFORM_OPTIONS.get(platform)
