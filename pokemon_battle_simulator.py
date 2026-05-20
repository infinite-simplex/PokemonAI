import struct
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import re
import json
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

showdown_proc = subprocess.Popen(
    ["node", str(ROOT_DIR / "server/ps.js")],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)
app = FastAPI()


def parse_c_defines(path, prefix):
    mapping = {}

    define_re = re.compile(
        rf"#define\s+{prefix}([A-Z0-9_]+)\s+(\d+)"
    )

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            match = define_re.match(line.strip())

            if not match:
                continue

            name = match.group(1)
            value = int(match.group(2))

            # Convert SHOWDOWN_FORMAT
            ps_name = (
                name.lower()
                .replace("_", "")
            )

            mapping[value] = ps_name

    return mapping

def decode_gba_string(raw_bytes: bytes) -> str:
    """Decodes raw GBA string buffers using the native character offsets."""
    decoded = []
    for b in raw_bytes:
        if b == 0xFF:  # Stop at Terminator code
            break
        decoded.append(GBA_CHAR_MAP.get(b, f"[{b:02X}]"))
    return "".join(decoded).strip()

# -------------------------------------------------------------------------
# SHOWDOWN TEAM PACKER
# -------------------------------------------------------------------------

def build_showdown_set(mon_dict):
    """
    Converts your parsed Pokémon dict into a Showdown-compatible set.
    """

    return {
        "species": mon_dict["species"].capitalize(),
        "name": mon_dict["nickname"],
        "item": "",
        "ability": "None",
        "moves": mon_dict["moves"],
        "nature": "Adamant",

        # Assume 0 EVs / IVs for now
        "evs": {
            "hp": 0,
            "atk": 0,
            "def": 0,
            "spa": 0,
            "spd": 0,
            "spe": 0,
        },

        "ivs": {
            "hp": 0,
            "atk": 0,
            "def": 0,
            "spa": 0,
            "spd": 0,
            "spe": 0,
        },

        "level": mon_dict["level"],
    }

class BattlePokemon:
    def __init__(self, raw_bytes: bytes):
        POKE_STRUCT_FMT = "<10sBBII4H4B4B8BHH"
        STRUCT_SIZE = struct.calcsize(POKE_STRUCT_FMT)  # Validates to exactly 48 bytes


        if len(raw_bytes) != STRUCT_SIZE:
            raise ValueError(f"Invalid byte size. Expected {STRUCT_SIZE}, got {len(raw_bytes)}")

        # Unpack binary buffer into raw components
        unpacked = struct.unpack(POKE_STRUCT_FMT, raw_bytes)

        # Extract variables from tuple
        self.nickname = decode_gba_string(unpacked[0])
        self.seen_flag = "PLAYER" if unpacked[1] == 0xAA else "ENEMY"
        self.level = unpacked[2]
        self.status1 = unpacked[3]
        self.status2 = unpacked[4]

        # Array-based extractions
        self.moves = list(unpacked[5:9])
        self.seen_moves = list(unpacked[9:13])
        self.pps = list(unpacked[13:17])
        self.stat_stages = list(unpacked[17:25])

        self.hp = unpacked[25]
        self.max_hp = unpacked[26]

    def display(self):
        """Prints a clean status card of the unpacked stats."""
        status_txt = "Healthy" if self.status1 == 0 else f"Condition Flags: {self.status1:08X}"
        print(f"  ● {self.nickname:<10} [Lv.{self.level:<2}]  HP: {self.hp}/{self.max_hp} ({status_txt})")
        print(f"    Moves:  " + " | ".join(f"ID:{m} (PP:{p})" for m, p in zip(self.moves, self.pps) if m != 0))
        print(
            f"    Stages: Atk:{self.stat_stages[1]} | Def:{self.stat_stages[2]} | Spd:{self.stat_stages[3]} | SpA:{self.stat_stages[4]} | SpD:{self.stat_stages[5]}")
        print("-" * 65)


# -------------------------------------------------------------------------
# 2. API REQUEST & ENDPOINT DEFINITIONS
# -------------------------------------------------------------------------
class BattleStatePayload(BaseModel):
    player: List[str]  # List of hexadecimal strings sent from Lua
    enemy: List[str]

def start_showdown_battle(player_team, enemy_team):
    """
    Sends battle initialization commands to your persistent ps.js process.
    """

    # Convert into Showdown team objects
    p1_sets = [build_showdown_set(mon) for mon in player_team]
    p2_sets = [build_showdown_set(mon) for mon in enemy_team]

    # Start battle
    showdown_proc.stdin.write(
        '>start {"formatid":"gen3ou"}\n'
    )

    # Send player 1
    showdown_proc.stdin.write(
        f'>player p1 {json.dumps({"name": "AI", "team": p1_sets})}\n'
    )

    # Send player 2
    showdown_proc.stdin.write(
        f'>player p2 {json.dumps({"name": "Enemy", "team": p2_sets})}\n'
    )

    showdown_proc.stdin.flush()

    print("\n[SHOWDOWN OUTPUT]")
    print("-" * 65)

    # Read several startup lines
    for _ in range(15):
        line = showdown_proc.stdout.readline()

        if not line:
            break

        print(line.strip())

# -------------------------------------------------------------------------
# GBA -> POKEMON SHOWDOWN CONVERSION
# -------------------------------------------------------------------------

def map_gba_to_ps(mon: BattlePokemon, species_id: int):
    """
    Converts a parsed GBA battle struct into a Showdown-compatible dict.
    """

    # ---------------------------------------------------------------------
    # STATUS
    # ---------------------------------------------------------------------

    if mon.status1 & 0x7:
        status = "slp"
    elif mon.status1 & 0x8:
        status = "psn"
    elif mon.status1 & 0x10:
        status = "brn"
    elif mon.status1 & 0x20:
        status = "frz"
    elif mon.status1 & 0x40:
        status = "par"
    elif mon.status1 & 0x80:
        status = "tox"
    else:
        status = None

    # ---------------------------------------------------------------------
    # MOVES
    # ---------------------------------------------------------------------

    moves = []

    for move_id in mon.moves:
        if move_id == 0:
            continue

        move_name = MOVE_ID_TO_PS.get(
            move_id,
            f"unknownmove{move_id}"
        )

        moves.append(move_name)

    # ---------------------------------------------------------------------
    # STAT BOOSTS
    # ---------------------------------------------------------------------

    boosts = {
        "atk": mon.stat_stages[1],
        "def": mon.stat_stages[2],
        "spe": mon.stat_stages[3],
        "spa": mon.stat_stages[4],
        "spd": mon.stat_stages[5],
        "accuracy": mon.stat_stages[0],
        "evasion": mon.stat_stages[6],
    }

    # ---------------------------------------------------------------------
    # SPECIES
    # ---------------------------------------------------------------------

    species = SPECIES_ID_TO_PS.get(
        species_id,
        f"unknownspecies{species_id}"
    )

    # ---------------------------------------------------------------------
    # RETURN SHOWDOWN DICT
    # ---------------------------------------------------------------------

    return {
        "species": species,
        "nickname": mon.nickname,
        "level": mon.level,

        "hp": mon.hp,
        "maxhp": mon.max_hp,

        "status": status,

        "moves": moves,

        "boosts": boosts,
    }

@app.post("/predict")
async def process_predict(payload: BattleStatePayload):
    print("\n" + "=" * 25 + " INCOMING BATTLE STATE " + "=" * 25)

    try:
        player_team = []
        enemy_team = []
        print("\n[YOUR PARTY]")
        print("-" * 65)
        for hex_str in payload.player:
            mon = BattlePokemon(bytes.fromhex(hex_str))
            mon.display()
            ps_mon = map_gba_to_ps(mon, species_id=25)
            player_team.append(ps_mon)

        print("\n[ENEMY PARTY]")
        print("-" * 65)
        for hex_str in payload.enemy:
            mon = BattlePokemon(bytes.fromhex(hex_str))
            mon.display()
            ps_mon = map_gba_to_ps(mon, species_id=94)
            enemy_team.append(ps_mon)

        # -----------------------------------------------------------------
        # START SHOWDOWN SIM
        # -----------------------------------------------------------------

        start_showdown_battle(
            player_team,
            enemy_team
        )

        # -----------------------------------------------------------------
        # TEMP DECISION
        # -----------------------------------------------------------------

        decision_byte = "0x01"

        print(f"Decision evaluated. Releasing GBA with: {decision_byte}")
        return decision_byte

    except Exception as e:
        print(f"Parsing error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# GBA text encoding translation map (Gen 3 English mapping fallback helper)
GBA_CHAR_MAP = {i: chr(i - 0xBB + ord('A')) for i in range(0xBB, 0xD4)}  # A-Z
GBA_CHAR_MAP.update({i: chr(i - 0xD5 + ord('a')) for i in range(0xD5, 0xEE)})  # a-z
GBA_CHAR_MAP[0x00] = ""  # End of String
GBA_CHAR_MAP[0xFF] = " "
MOVE_ID_TO_PS = parse_c_defines(
    ROOT_DIR / "pokeemerald/include/constants/moves.h",
    "MOVE_"
)

SPECIES_ID_TO_PS = parse_c_defines(
    ROOT_DIR / "pokeemerald/include/constants/species.h",
    "SPECIES_"
)

if __name__ == "__main__":
    import uvicorn

    # -------------------------------------------------------------------------
    # 1. POKÉMON DATA STRUCTURE & PARSER
    # -------------------------------------------------------------------------
    # The structural byte format for struct.unpack matching your 48-byte layout:
    #  - <  : Little-endian (Standard GBA ARM architecture)
    #  - 10s: 10 bytes for Nickname (char array)
    #  - B  : 1 byte for Seen flag
    #  - B  : 1 byte for Level
    #  - I  : 4 bytes (uint32) for Status1
    #  - I  : 4 bytes (uint32) for Status2
    #  - 4H : 8 bytes total (4 moves * uint16)
    #  - 4B : 4 bytes total (4 moves * uint8) for Seen Move flags
    #  - 4B : 4 bytes total (4 moves * uint8) for current PPs
    #  - 8B : 8 bytes total (8 stat stages * uint8)
    #  - H  : 2 bytes (uint16) for current HP
    #  - H  : 2 bytes (uint16) for Max HP

    # Start the server locally
    uvicorn.run(app, host="127.0.0.1", port=8080)
