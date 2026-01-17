"""System migracji bazy danych."""

from .migrator import Migrator, run_migrations

__all__ = ['Migrator', 'run_migrations']
