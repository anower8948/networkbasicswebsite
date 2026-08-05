"""Passenger entry point for cPanel's "Setup Python App".

cPanel runs Python applications under Phusion Passenger, which speaks **WSGI**.
This application is **ASGI** (FastAPI), so the two need a bridge —
`a2wsgi.ASGIMiddleware` — and that bridge is the reason this file exists.

What that costs, stated plainly: WSGI is synchronous, so every request occupies
a worker for its whole duration and the async database driver's concurrency
advantage is lost. It works, and it is the only way to run this on shared
hosting, but a VPS or App Service will serve several times the throughput on the
same hardware. Use cPanel when cPanel is the constraint, not by preference.

Setup:
  1. cPanel → Setup Python App → Python 3.12, application root `nlp`,
     application URL `/`, startup file `passenger_wsgi.py`.
  2. Enter the virtualenv shown by cPanel, then:
       pip install -e ./backend
       pip install a2wsgi
  3. Add the environment variables from `infra/vps/api.env.example` in the
     app's Environment Variables panel — cPanel injects them into the process.
  4. `alembic upgrade head` from the cPanel terminal, once.
  5. Upload the built frontend (`npm run build`) to `public_html`, and put the
     `.htaccess` from this directory beside it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# cPanel starts the process with the application root as cwd, but the backend
# package lives one level in and is not otherwise importable.
APPLICATION_ROOT = Path(__file__).resolve().parent
BACKEND = APPLICATION_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Shared hosting has no supervisor to catch a bad configuration, so make the
# production guards apply here too rather than silently running in dev mode.
os.environ.setdefault("ENVIRONMENT", "production")

from a2wsgi import ASGIMiddleware  # noqa: E402  (path set up above)

from app.main import app as asgi_app  # noqa: E402

# Passenger looks for a module-level callable named exactly `application`.
application = ASGIMiddleware(asgi_app)
