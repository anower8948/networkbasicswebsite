"""Application services — business rules, independent of HTTP and ORM details.

Deliberately empty of re-exports. Eagerly importing every service here means
importing *any* one of them pulls in *all* of them, which created a genuine
circular import: `app.schemas.topology` imports `device_catalog`, importing that
submodule runs this file, and this file imported `topology_service`, which
imports `app.schemas.topology` while it is still initialising.

Import concrete modules instead — `from app.services.auth_service import
AuthService` — which is what every call site already does.
"""
