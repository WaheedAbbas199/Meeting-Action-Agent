from alembic import context
from app import models  # noqa: F401  (register tables)
from app.config import get_settings
from app.db import Base, make_engine

target_metadata = Base.metadata


def run() -> None:
    url = get_settings().database_url
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = make_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=url.startswith("sqlite"), compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run()
