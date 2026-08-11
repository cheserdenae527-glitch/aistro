from app.api.v1.auth import router as auth_router
from app.api.v1.merchants import router as merchants_router
from app.api.v1.shops import router as shops_router
from app.api.v1.crawl_jobs import router as crawl_jobs_router
from app.api.v1.images import router as images_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.notes import router as notes_router
from app.api.v1.profiles import router as profiles_router
from app.api.v1.designs import router as designs_router
from app.api.v1.reviews import router as reviews_router
from app.api.v1.studio import router as studio_router
from app.api.v1.maps import router as maps_router
from app.api.v1.district import router as district_router
from app.api.v1.deals import router as deals_router
from app.api.v1.live import router as live_router
from app.api.v1.media import router as media_router
from app.api.v1.settings import router as settings_router
from app.api.v1.browser_bridge import router as browser_bridge_router
from app.api.v1.knowledge import router as knowledge_router

routers = [auth_router, merchants_router, shops_router, crawl_jobs_router, notes_router, images_router, subscriptions_router, profiles_router, designs_router, reviews_router, studio_router, maps_router, district_router, deals_router, live_router, media_router, settings_router, browser_bridge_router, knowledge_router]
