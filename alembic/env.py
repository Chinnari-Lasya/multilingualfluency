import os
from alembic import context
from sqlalchemy import create_engine
from gec_api.db import Base, database_url

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(os.environ.get("GEC_DATABASE_URL") or database_url())
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
