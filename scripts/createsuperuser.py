"""
Usage:
    docker compose exec api python scripts/createsuperuser.py
"""
import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.users.models import User


async def main() -> None:
    email = input("Email: ").strip()
    full_name = input("Full name: ").strip() or None
    password = input("Password: ").strip()
    confirm = input("Confirm password: ").strip()

    if password != confirm:
        print("Passwords do not match.")
        return

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            print(f"User with email '{email}' already exists.")
            return

        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            is_active=True,
            is_admin=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    print(f"Superuser '{email}' created successfully.")


if __name__ == "__main__":
    asyncio.run(main())
