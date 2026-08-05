"""Repositories — the only place SQLAlchemy queries are constructed.

Intentionally free of re-exports; see `app.services.__init__` for why. Import
concrete modules: `from app.repositories.user import UserRepository`.
"""
