import logging
import uuid
from typing import Optional

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.follower import Follower

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for user and follower data access."""

    @staticmethod
    async def create_user(
        session: AsyncSession,
        username: str,
        email: str,
        password_hash: str,
    ) -> User:
        """Insert a new user into the database."""
        user = User(
            username=username,
            email=email,
            password_hash=password_hash,
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)
        logger.info("Created user: %s (id=%s)", username, user.id)
        return user

    @staticmethod
    async def get_by_id(
        session: AsyncSession, user_id: uuid.UUID
    ) -> Optional[User]:
        """Fetch a user by their UUID."""
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_username(
        session: AsyncSession, username: str
    ) -> Optional[User]:
        """Fetch a user by username."""
        result = await session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(
        session: AsyncSession, email: str
    ) -> Optional[User]:
        """Fetch a user by email."""
        result = await session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_follow(
        session: AsyncSession,
        follower_id: uuid.UUID,
        followee_id: uuid.UUID,
    ) -> Follower:
        """Create a follow relationship."""
        follow = Follower(follower_id=follower_id, followee_id=followee_id)
        session.add(follow)
        await session.flush()
        logger.info("User %s followed %s", follower_id, followee_id)
        return follow

    @staticmethod
    async def delete_follow(
        session: AsyncSession,
        follower_id: uuid.UUID,
        followee_id: uuid.UUID,
    ) -> bool:
        """Delete a follow relationship. Returns True if a row was deleted."""
        result = await session.execute(
            delete(Follower).where(
                Follower.follower_id == follower_id,
                Follower.followee_id == followee_id,
            )
        )
        deleted = result.rowcount > 0
        if deleted:
            logger.info("User %s unfollowed %s", follower_id, followee_id)
        return deleted

    @staticmethod
    async def is_following(
        session: AsyncSession,
        follower_id: uuid.UUID,
        followee_id: uuid.UUID,
    ) -> bool:
        """Check if follower_id follows followee_id."""
        result = await session.execute(
            select(Follower).where(
                Follower.follower_id == follower_id,
                Follower.followee_id == followee_id,
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def increment_follower_count(
        session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        """Increment the follower_count for a user by 1."""
        user = await session.get(User, user_id)
        if user:
            user.follower_count += 1
            await session.flush()

    @staticmethod
    async def decrement_follower_count(
        session: AsyncSession, user_id: uuid.UUID
    ) -> None:
        """Decrement the follower_count for a user by 1 (min 0)."""
        user = await session.get(User, user_id)
        if user:
            user.follower_count = max(0, user.follower_count - 1)
            await session.flush()

    @staticmethod
    async def get_follower_count(
        session: AsyncSession, user_id: uuid.UUID
    ) -> int:
        """Get the follower_count for a user."""
        user = await session.get(User, user_id)
        return user.follower_count if user else 0

    @staticmethod
    async def get_followers(
        session: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """Get paginated list of followers for a user."""
        # Count total
        count_result = await session.execute(
            select(func.count()).select_from(Follower).where(
                Follower.followee_id == user_id
            )
        )
        total = count_result.scalar_one()

        # Fetch users
        result = await session.execute(
            select(User)
            .join(Follower, Follower.follower_id == User.id)
            .where(Follower.followee_id == user_id)
            .order_by(Follower.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        users = list(result.scalars().all())
        return users, total

    @staticmethod
    async def get_following(
        session: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """Get paginated list of users that user_id is following."""
        count_result = await session.execute(
            select(func.count()).select_from(Follower).where(
                Follower.follower_id == user_id
            )
        )
        total = count_result.scalar_one()

        result = await session.execute(
            select(User)
            .join(Follower, Follower.followee_id == User.id)
            .where(Follower.follower_id == user_id)
            .order_by(Follower.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        users = list(result.scalars().all())
        return users, total

    @staticmethod
    async def get_all_follower_ids(
        session: AsyncSession, user_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Get all follower IDs for a user (used in fan-out)."""
        result = await session.execute(
            select(Follower.follower_id).where(
                Follower.followee_id == user_id
            )
        )
        return [row[0] for row in result.all()]

    @staticmethod
    async def get_following_ids(
        session: AsyncSession, user_id: uuid.UUID
    ) -> list[uuid.UUID]:
        """Get all user IDs that user_id is following."""
        result = await session.execute(
            select(Follower.followee_id).where(
                Follower.follower_id == user_id
            )
        )
        return [row[0] for row in result.all()]

    @staticmethod
    async def search_by_username(
        session: AsyncSession,
        query: str,
        limit: int = 20,
    ) -> list["User"]:
        """Search users by username prefix (case-insensitive)."""
        result = await session.execute(
            select(User)
            .where(User.username.ilike(f"%{query}%"))
            .order_by(User.username)
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_celebrity_followee_ids(
        session: AsyncSession,
        user_id: uuid.UUID,
        celebrity_threshold: int,
    ) -> list[uuid.UUID]:
        """Get IDs of followees who are celebrities (follower_count > threshold)."""
        result = await session.execute(
            select(User.id)
            .join(Follower, Follower.followee_id == User.id)
            .where(
                Follower.follower_id == user_id,
                User.follower_count > celebrity_threshold,
            )
        )
        return [row[0] for row in result.all()]
