import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.kafka.producer import kafka_producer
from app.repositories.user_repo import UserRepository
from app.schemas.user import RegisterRequest, UserResponse, UserProfileResponse
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


class UserService:
    """Service layer for user operations."""

    @staticmethod
    async def register(
        write_db: AsyncSession,
        request: RegisterRequest,
    ) -> UserResponse:
        """Register a new user."""
        # Check duplicate username
        existing = await UserRepository.get_by_username(write_db, request.username)
        if existing:
            raise HTTPException(
                status_code=400,
                detail={"detail": "Username already taken", "code": "DUPLICATE_USERNAME"},
            )

        # Check duplicate email
        existing_email = await UserRepository.get_by_email(write_db, request.email)
        if existing_email:
            raise HTTPException(
                status_code=400,
                detail={"detail": "Email already registered", "code": "DUPLICATE_EMAIL"},
            )

        password_hash = AuthService.hash_password(request.password)
        user = await UserRepository.create_user(
            write_db, request.username, request.email, password_hash
        )
        return UserResponse.model_validate(user)

    @staticmethod
    async def login(
        read_db: AsyncSession,
        username: str,
        password: str,
    ) -> dict:
        """Authenticate user and return JWT token."""
        user = await UserRepository.get_by_username(read_db, username)
        if not user:
            raise HTTPException(
                status_code=401,
                detail={"detail": "Invalid credentials", "code": "INVALID_CREDENTIALS"},
            )
        if not AuthService.verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=401,
                detail={"detail": "Invalid credentials", "code": "INVALID_CREDENTIALS"},
            )
        token = AuthService.create_access_token(
            user_id=str(user.id), username=user.username
        )
        return {"access_token": token, "token_type": "bearer"}

    @staticmethod
    async def get_profile(
        read_db: AsyncSession,
        user_id: uuid.UUID,
    ) -> UserProfileResponse:
        """Get a user's public profile."""
        user = await UserRepository.get_by_id(read_db, user_id)
        if not user:
            raise HTTPException(
                status_code=404,
                detail={"detail": "User not found", "code": "USER_NOT_FOUND"},
            )
        return UserProfileResponse.model_validate(user)

    @staticmethod
    async def follow(
        write_db: AsyncSession,
        follower_id: uuid.UUID,
        followee_id: uuid.UUID,
    ) -> dict:
        """Follow a user."""
        if follower_id == followee_id:
            raise HTTPException(
                status_code=400,
                detail={"detail": "Cannot follow yourself", "code": "SELF_FOLLOW"},
            )

        # Check followee exists
        followee = await UserRepository.get_by_id(write_db, followee_id)
        if not followee:
            raise HTTPException(
                status_code=404,
                detail={"detail": "User not found", "code": "USER_NOT_FOUND"},
            )

        # Check not already following
        already = await UserRepository.is_following(write_db, follower_id, followee_id)
        if already:
            raise HTTPException(
                status_code=400,
                detail={"detail": "Already following this user", "code": "ALREADY_FOLLOWING"},
            )

        await UserRepository.create_follow(write_db, follower_id, followee_id)
        await UserRepository.increment_follower_count(write_db, followee_id)

        # Publish follow event to Kafka
        await kafka_producer.send(
            topic="follow.created",
            value={
                "follower_id": str(follower_id),
                "followee_id": str(followee_id),
            },
        )
        logger.info("User %s followed %s", follower_id, followee_id)
        return {"detail": "Successfully followed user"}

    @staticmethod
    async def unfollow(
        write_db: AsyncSession,
        follower_id: uuid.UUID,
        followee_id: uuid.UUID,
    ) -> dict:
        """Unfollow a user."""
        if follower_id == followee_id:
            raise HTTPException(
                status_code=400,
                detail={"detail": "Cannot unfollow yourself", "code": "SELF_UNFOLLOW"},
            )

        deleted = await UserRepository.delete_follow(
            write_db, follower_id, followee_id
        )
        if not deleted:
            raise HTTPException(
                status_code=400,
                detail={"detail": "Not following this user", "code": "NOT_FOLLOWING"},
            )

        await UserRepository.decrement_follower_count(write_db, followee_id)

        # Publish unfollow event to Kafka
        await kafka_producer.send(
            topic="follow.deleted",
            value={
                "follower_id": str(follower_id),
                "followee_id": str(followee_id),
            },
        )
        logger.info("User %s unfollowed %s", follower_id, followee_id)
        return {"detail": "Successfully unfollowed user"}

    @staticmethod
    async def get_followers(
        read_db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Get paginated list of followers."""
        users, total = await UserRepository.get_followers(
            read_db, user_id, limit, offset
        )
        return {
            "users": [UserProfileResponse.model_validate(u) for u in users],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    async def get_following(
        read_db: AsyncSession,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Get paginated list of users being followed."""
        users, total = await UserRepository.get_following(
            read_db, user_id, limit, offset
        )
        return {
            "users": [UserProfileResponse.model_validate(u) for u in users],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @staticmethod
    async def search_users(
        read_db: AsyncSession,
        query: str,
        limit: int = 20,
    ) -> list:
        """Search users by username."""
        users = await UserRepository.search_by_username(read_db, query, limit)
        return [UserProfileResponse.model_validate(u) for u in users]
