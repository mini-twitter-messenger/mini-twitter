"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('username', sa.String(50), unique=True, nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('follower_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )

    # Tweets table
    op.create_table(
        'tweets',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint('char_length(content) <= 280', name='ck_tweet_content_length'),
    )

    # Followers table
    op.create_table(
        'followers',
        sa.Column('follower_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('followee_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('follower_id', 'followee_id'),
    )

    # Indexes
    op.create_index('idx_tweets_user_created', 'tweets', ['user_id', sa.text('created_at DESC')])
    op.create_index('idx_followers_followee', 'followers', ['followee_id'])
    op.create_index('idx_followers_follower', 'followers', ['follower_id'])


def downgrade() -> None:
    op.drop_index('idx_followers_follower', table_name='followers')
    op.drop_index('idx_followers_followee', table_name='followers')
    op.drop_index('idx_tweets_user_created', table_name='tweets')
    op.drop_table('followers')
    op.drop_table('tweets')
    op.drop_table('users')
