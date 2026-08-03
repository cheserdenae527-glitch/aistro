"""开发种子数据。"""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.security import hash_password
from app.models import User, Merchant, Shop, PlatformShop, Review


async def seed():
    engine = create_async_engine(
        "postgresql+asyncpg://aistro:aistro@localhost:5432/aistro"
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        # 用户
        user = User(
            id=uuid.uuid4(),
            email="admin@test.com",
            password_hash=hash_password("admin123"),
            name="运营团队",
            role="admin",
        )
        db.add(user)
        await db.flush()

        # 商家
        m1 = Merchant(
            id=uuid.uuid4(),
            user_id=user.id,
            name="川味坊火锅",
            contact_name="张老板",
            contact_phone="13800138001",
            tier="pro",
        )
        m2 = Merchant(
            id=uuid.uuid4(),
            user_id=user.id,
            name="星巴克咖啡",
            contact_name="李店长",
            contact_phone="13800138002",
            tier="enterprise",
        )
        db.add_all([m1, m2])
        await db.flush()

        # 川味坊门店
        s1 = Shop(
            id=uuid.uuid4(),
            merchant_id=m1.id,
            name="川味坊火锅·解放碑店",
            address="重庆市渝中区解放碑步行街88号",
            category="火锅",
        )
        s2 = Shop(
            id=uuid.uuid4(),
            merchant_id=m1.id,
            name="川味坊火锅·观音桥店",
            address="重庆市江北区观音桥步行街66号",
            category="火锅",
        )
        s3 = Shop(
            id=uuid.uuid4(),
            merchant_id=m1.id,
            name="川味坊火锅·南坪店",
            address="重庆市南岸区南坪西路22号",
            category="火锅",
        )

        # 星巴克门店
        s4 = Shop(
            id=uuid.uuid4(),
            merchant_id=m2.id,
            name="星巴克咖啡·时代天街店",
            address="重庆市渝中区大坪时代天街B1",
            category="咖啡",
        )
        s5 = Shop(
            id=uuid.uuid4(),
            merchant_id=m2.id,
            name="星巴克咖啡·万象城店",
            address="重庆市九龙坡区谢家湾万象城L1",
            category="咖啡",
        )
        db.add_all([s1, s2, s3, s4, s5])
        await db.flush()

        # 平台店铺绑定
        for shop in [s1, s2, s3]:
            db.add(
                PlatformShop(
                    shop_id=shop.id,
                    platform="meituan",
                    shop_name=shop.name,
                )
            )
            db.add(
                PlatformShop(
                    shop_id=shop.id,
                    platform="douyin",
                    shop_name=shop.name,
                )
            )

        # 示例评价（川味坊解放碑店）
        platform = PlatformShop(shop_id=s1.id, platform="meituan", shop_name=s1.name)
        db.add(platform)
        await db.flush()

        reviews_data = [
            Review(
                platform_shop_id=platform.id,
                reviewer_name="吃货小王",
                rating=5,
                content="味道非常好，麻辣鲜香，下次还会来！",
                sentiment="positive",
            ),
            Review(
                platform_shop_id=platform.id,
                reviewer_name="美食猎人",
                rating=2,
                content="等位太久，上菜速度太慢了，体验不好。",
                sentiment="negative",
            ),
            Review(
                platform_shop_id=platform.id,
                reviewer_name="火锅爱好者",
                rating=4,
                content="整体不错，装修很有特色，但价格偏贵。",
                sentiment="positive",
            ),
        ]
        db.add_all(reviews_data)

        await db.commit()
        print(f"Seed complete: {user.email} / admin123")


if __name__ == "__main__":
    asyncio.run(seed())
