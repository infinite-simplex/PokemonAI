import sys
import json
import asyncio

from pathlib import Path

# -------------------------------------------------------------------------
# ADD PROJECT ROOT
# -------------------------------------------------------------------------

sys.path.append(
    str(Path(__file__).resolve().parent.parent)
)

# -------------------------------------------------------------------------
# IMPORT SIMULATOR
# -------------------------------------------------------------------------

from pokemon_battle_simulator import (
    process_predict,
    BattleStatePayload
)

# -------------------------------------------------------------------------
# PATHS
# -------------------------------------------------------------------------

TEST_DIR = Path(__file__).resolve().parent

# -------------------------------------------------------------------------
# TEST
# -------------------------------------------------------------------------

async def run_test():

    with open(TEST_DIR / "test1.json", "r") as f:
        data = json.load(f)

    payload = BattleStatePayload(**data)

    result = await process_predict(payload)

    print("\nRESULT:")
    print(result)


if __name__ == "__main__":
    asyncio.run(run_test())