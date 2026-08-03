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

routers = [auth_router, merchants_router, shops_router, crawl_jobs_router, notes_router, images_router, subscriptions_router, profiles_router, designs_router, reviews_router]




