from app.services.boss_service import BossPlatformService
from app.services.liepin_service import LiepinPlatformService
from app.services.zhilian_service import ZhilianPlatformService

boss_service = BossPlatformService()
liepin_service = LiepinPlatformService()
zhilian_service = ZhilianPlatformService()

PLATFORM_SERVICES = {
    "boss": boss_service,
    "liepin": liepin_service,
    "zhilian": zhilian_service,
}


def get_platform_service(platform: str):
    return PLATFORM_SERVICES.get(platform)
