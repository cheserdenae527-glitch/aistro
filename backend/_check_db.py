import asyncio
from sqlalchemy import text
from app.core.database import engine

async def check():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name"))
        tables = [r[0] for r in result]
        print("Tables:", tables)
        assert "shop_profiles" in tables, "shop_profiles missing!"
        print("OK: shop_profiles table exists")
    await engine.dispose()

asyncio.run(check())
