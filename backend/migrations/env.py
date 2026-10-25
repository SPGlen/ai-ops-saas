import os
from alembic import context
from sqlalchemy import create_engine, pool
from sqlmodel import SQLModel
from app import models
from app.config import settings

url = os.environ.get("OPS_MIGRATION_DATABASE_URL")
if not url:
    raise RuntimeError("OPS_MIGRATION_DATABASE_URL must use migration credentials")
if not url.startswith("postgresql"):
    raise RuntimeError("Migrations require PostgreSQL")
if context.is_offline_mode():
    context.configure(
        url=url,
        target_metadata=SQLModel.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(
            connection=conn, target_metadata=SQLModel.metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()
