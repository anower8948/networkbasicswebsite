"""`python -m app.seeds` — seed the catalogue."""

import asyncio

from app.seeds.runner import main

asyncio.run(main())
