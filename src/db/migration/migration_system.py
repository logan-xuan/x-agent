"""
Database migration system for the x-agent2 AI assistant system.

This module provides functionality for managing database schema changes
using SQLAlchemy migrations.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from src.db.models import Base  # Assuming Base is defined in models
from src.agent_core.config.config_service import get_config


class DatabaseMigrationManager:
    """Manages database schema migrations."""

    def __init__(self, database_url: Optional[str] = None):
        self.config = get_config()
        self.database_url = database_url or self.config.database.get_database_url()
        self.alembic_cfg = self._setup_alembic_config()

        # Create migrations directory if it doesn't exist
        self.migrations_dir = Path("migrations")
        self.migrations_dir.mkdir(exist_ok=True)

    def _setup_alembic_config(self) -> Config:
        """Set up Alembic configuration."""
        alembic_cfg = Config()

        # Create alembic.ini content
        alembic_ini_content = f"""[alembic]
script_location = migrations
sqlalchemy.url = {self.database_url}

[post_write_hooks]
# Logging configuration
[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
"""

        # Write alembic.ini file
        alembic_ini_path = Path("alembic.ini")
        if not alembic_ini_path.exists():
            with open(alembic_ini_path, 'w') as f:
                f.write(alembic_ini_content)

        alembic_cfg.set_main_option("script_location", str(self.migrations_dir))
        alembic_cfg.set_main_option("sqlalchemy.url", self.database_url)

        return alembic_cfg

    def init_migration_environment(self):
        """Initialize the migration environment if not already set up."""
        if not (self.migrations_dir / "env.py").exists():
            # Create the migration environment
            env_py_content = '''import logging
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Import your models here
from src.db.models.base import Base  # Adjust import based on your structure
from src.db.models.user import User
from src.db.models.session import Session
from src.db.models.message import Message
from src.db.models.plugin import Plugin
from src.db.models.memory_entry import MemoryEntry
from src.db.models.task import Task
from src.db.models.interaction_trace import InteractionTrace
from src.db.models.subagent import SubAgent
from src.db.models.configuration import Configuration
from src.db.models.subagent_execution import SubAgentExecution
from src.db.models.scheduled_task import ScheduledTask
from src.db.models.tool_execution import ToolExecution

# This line sets up loggers basically.
try:
    fileConfig(context.config.config_file_name)
except Exception:
    pass

# Add your model"s MetaData object here for "autogenerate" support
target_metadata = Base.metadata

def run_migrations_offline():
    """Run migrations in "offline" mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don"t even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = context.config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in "online" mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        context.config.get_section(context.config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''

            # Create migration directory structure
            self.migrations_dir.mkdir(exist_ok=True)

            # Create versions subdirectory
            (self.migrations_dir / "versions").mkdir(exist_ok=True)

            # Write env.py
            with open(self.migrations_dir / "env.py", "w") as f:
                f.write(env_py_content)

            # Create initial version file
            readme_content = "# Alembic Migrations\n\nThis directory contains database migration files."
            with open(self.migrations_dir / "README", "w") as f:
                f.write(readme_content)

            # Create __init__.py
            with open(self.migrations_dir / "__init__.py", "w") as f:
                f.write("# Migration package")

    def create_initial_migration(self, message: str = "Initial migration"):
        """Create the initial migration based on current models."""
        self.init_migration_environment()

        try:
            # Create the initial migration
            command.revision(
                self.alembic_cfg,
                autogenerate=True,
                message=message,
                sql=False
            )
        except Exception as e:
            print(f"Error creating initial migration: {e}")
            # If autogenerate fails, create empty migration
            command.revision(
                self.alembic_cfg,
                message=message,
                autogenerate=False
            )

    def run_migrations(self, revision: str = "head"):
        """Run pending migrations to update the database schema."""
        try:
            command.upgrade(self.alembic_cfg, revision)
            print(f"Successfully migrated to revision: {revision}")
        except Exception as e:
            print(f"Error running migrations: {e}")
            raise

    def downgrade_migrations(self, revision: str):
        """Downgrade the database schema to a previous revision."""
        try:
            command.downgrade(self.alembic_cfg, revision)
            print(f"Successfully downgraded to revision: {revision}")
        except Exception as e:
            print(f"Error downgrading migrations: {e}")
            raise

    def get_current_revision(self) -> Optional[str]:
        """Get the current migration revision."""
        try:
            # Connect to the database and check alembic version table
            engine = create_engine(self.database_url)

            with engine.connect() as conn:
                try:
                    # Check if alembic_version table exists
                    result = conn.execute(text("SELECT version_num FROM alembic_version"))
                    row = result.fetchone()
                    if row:
                        return row[0]
                    return None
                except Exception:
                    # Table doesn't exist, meaning no migrations have been run
                    return None
        except Exception as e:
            print(f"Error getting current revision: {e}")
            return None

    def list_migrations(self) -> List[dict]:
        """List all available migrations."""
        try:
            script_dir = ScriptDirectory.from_config(self.alembic_cfg)
            revisions = []

            for script in script_dir.walk_revisions():
                revisions.append({
                    "revision": script.revision,
                    "down_revision": script.down_revision,
                    "dependencies": script.dependencies,
                    "message": script.doc,
                    "path": str(script.path) if hasattr(script, 'path') else None
                })

            return revisions
        except Exception as e:
            print(f"Error listing migrations: {e}")
            return []

    def stamp_revision(self, revision: str):
        """Stamp the database with the given revision without running migrations."""
        try:
            command.stamp(self.alembic_cfg, revision)
            print(f"Successfully stamped database with revision: {revision}")
        except Exception as e:
            print(f"Error stamping revision: {e}")
            raise

    def check_pending_migrations(self) -> bool:
        """Check if there are pending migrations to apply."""
        try:
            engine = create_engine(self.database_url)

            # Get current revision from DB
            current_rev = self.get_current_revision()

            # Get the head revision from migration files
            script_dir = ScriptDirectory.from_config(self.alembic_cfg)
            head_revision = script_dir.get_current_head()

            return current_rev != head_revision
        except Exception:
            # If we can't determine, assume there are pending migrations
            return True

    def create_custom_migration(self, message: str, upgrade_sql: str, downgrade_sql: str = ""):
        """Create a custom migration with provided SQL statements."""
        try:
            # Create a custom migration script
            revision_id = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{message.lower().replace(' ', '_')}"
            revision_file = self.migrations_dir / "versions" / f"{revision_id}.py"

            # Generate migration template
            migration_content = f'''"""{message}

Revision ID: {revision_id}
Revises:
Create Date: {datetime.utcnow().isoformat()}

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text  # Import text for raw SQL execution

# revision identifiers, used by Alembic.
revision = "{revision_id}"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Apply upgrade migrations."""
    # ### commands auto generated by Alembic - please adjust! ###
    {upgrade_sql}
    # ### end Alembic commands ###


def downgrade():
    """Revert upgrade migrations."""
    # ### commands auto generated by Alembic - please adjust! ###
    {downgrade_sql if downgrade_sql else '# No downgrade available'}
    # ### end Alembic commands ###
'''

            with open(revision_file, 'w') as f:
                f.write(migration_content)

            print(f"Custom migration created: {revision_file}")
            return str(revision_file)
        except Exception as e:
            print(f"Error creating custom migration: {e}")
            raise

    def ensure_database_exists(self):
        """Ensure the database exists, creating it if necessary."""
        # Extract database name from URL
        db_name = self.database_url.split('/')[-1]

        # Create engine for the main postgres database to create new database
        base_url = self.database_url.rsplit('/', 1)[0] + '/postgres'

        try:
            engine = create_engine(base_url)
            with engine.connect() as conn:
                # Check if database exists
                result = conn.execute(text(
                    "SELECT 1 FROM pg_database WHERE datname=:database_name"
                ), {"database_name": db_name})

                if not result.fetchone():
                    # Database doesn't exist, create it
                    conn.execute(text(f"CREATE DATABASE {db_name}"))
                    conn.commit()
                    print(f"Database {db_name} created successfully")
        except Exception as e:
            print(f"Error ensuring database exists: {e}")
            # If PostgreSQL-specific approach fails, continue assuming database exists


class MigrationRunner:
    """Utility class to run migrations in different environments."""

    def __init__(self):
        self.manager = DatabaseMigrationManager()

    def setup_dev_database(self):
        """Set up database for development environment."""
        print("Setting up development database...")
        self.manager.ensure_database_exists()
        self.manager.init_migration_environment()

        # Create initial migration if needed
        if not self.manager.get_current_revision():
            self.manager.create_initial_migration("Development setup")

        # Apply migrations
        self.manager.run_migrations()
        print("Development database setup complete.")

    def setup_test_database(self):
        """Set up database for testing environment."""
        print("Setting up test database...")
        # For testing, we might want a separate DB or recreate the test DB
        self.manager.ensure_database_exists()
        self.manager.run_migrations()
        print("Test database setup complete.")

    def migrate_production(self):
        """Run migrations for production environment."""
        print("Running production migrations...")
        self.manager.run_migrations()
        print("Production migrations complete.")


# Global migration manager instance
migration_manager = DatabaseMigrationManager()


# Convenience functions
def run_migrations(revision: str = "head"):
    """Run database migrations."""
    migration_manager.run_migrations(revision)


def create_initial_migration(message: str = "Initial migration"):
    """Create the initial migration."""
    migration_manager.create_initial_migration(message)


def check_pending_migrations() -> bool:
    """Check if there are pending migrations."""
    return migration_manager.check_pending_migrations()


def get_current_revision() -> Optional[str]:
    """Get the current migration revision."""
    return migration_manager.get_current_revision()