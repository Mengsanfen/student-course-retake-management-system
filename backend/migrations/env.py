from alembic import context

from app.config import Settings
from app.database import make_engine
from app.models import metadata

config = context.config
target_metadata = metadata


def run_migrations():
    if context.is_offline_mode():
        context.configure(
            url=Settings.from_env().database_url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    supplied = config.attributes.get("connection")
    if supplied is not None:
        context.configure(connection=supplied, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = make_engine(Settings.from_env().database_url)
        try:
            with engine.connect() as connection:
                context.configure(connection=connection, target_metadata=target_metadata)
                with context.begin_transaction():
                    context.run_migrations()
        finally:
            engine.dispose()


run_migrations()
