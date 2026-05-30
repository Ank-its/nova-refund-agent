"""Allow `python -m app.seed` to run the seeder."""
from __future__ import annotations

import asyncio

from app.seed.data import seed

if __name__ == "__main__":
    asyncio.run(seed())
