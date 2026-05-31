import struct
import socket
import json
from pydantic import BaseModel
from typing import List
import re
import json
import subprocess
from pathlib import Path
import time
DISPLAY_USE_NAMES = True  # Toggle: True = human-readable names, False = raw byte values
NATURES = [
    "Hardy",
    "Lonely",
    "Brave",
    "Adamant",
    "Naughty",
    "Bold",
    "Docile",
    "Relaxed",
    "Impish",
    "Lax",
    "Timid",
    "Hasty",
    "Serious",
    "Jolly",
    "Naive",
    "Modest",
    "Mild",
    "Quiet",
    "Bashful",
    "Rash",
    "Calm",
    "Gentle",
    "Sassy",
    "Careful",
    "Quirky",
]

ROOT_DIR = Path(__file__).resolve().parent

showdown_proc = subprocess.Popen(
    ["node", str(ROOT_DIR / "ps.js")],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1
)
time.sleep(1)

if showdown_proc.poll() is None:
    print("Process is still running")
else:
    print(f"Process exited with code {showdown_proc.returncode}")
    print(showdown_proc.stderr.read())
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
            if name == 'COUNT':
                break
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
    return {
        "species": mon_dict["species"].capitalize(),
        "name": mon_dict.get("nickname", ""),
        "item": mon_dict.get("item", ""),
        "ability": "None",
        "moves": mon_dict["moves"],
        "nature": mon_dict.get("nature", "Hardy"),

        "evs": mon_dict.get("evs", {
            "hp": 0,
            "atk": 0,
            "def": 0,
            "spa": 0,
            "spd": 0,
            "spe": 0,
        }),

        "ivs": mon_dict.get("ivs", {
            "hp": 31,
            "atk": 31,
            "def": 31,
            "spa": 31,
            "spd": 31,
            "spe": 31,
        }),

        "level": mon_dict["level"],
    }


class BattlePokemon:
    NUM_MOVES = 4
    NUM_STATS = 8

    # Exact struct layout from C
    #
    # u16 species
    # u16 attack
    # u16 defense
    # u16 speed
    # u16 spAttack
    # u16 spDefense
    # u16 moves[4]
    # u16 hp
    # u16 maxHP
    # u16 item
    # u8 level
    # u8 friendship
    # u32 personality
    # u32 status1
    # u32 status2
    # s8 statStages[8]
    # u8 pp[4]
    # u8 seen_move[4]
    # u8 ppBonuses
    # u8 isEgg
    # u8 gender
    # u8 nature
    # u8 hpEV
    # u8 atkEV
    # u8 defEV
    # u8 speedEV
    # u8 spAtkEV
    # u8 spDefEV
    # u8 hpIV
    # u8 atkIV
    # u8 defIV
    # u8 speedIV
    # u8 spAtkIV
    # u8 spDefIV
    # u8 abilityNum
    # u8 seen

    POKE_STRUCT_FMT = (
        "<"  # little endian

        # core stats
        "H"  # species
        "H"  # attack
        "H"  # defense
        "H"  # speed
        "H"  # spAttack
        "H"  # spDefense

        # moves
        "4H"  # moves[4]

        # hp/item
        "H"  # hp
        "H"  # maxHP
        "H"  # item

        # misc
        "B"  # level
        "B"  # friendship

        # statuses
        "I"  # personality
        "I"  # status1
        "I"  # status2

        # stages
        "8b"  # statStages[8]

        # pp
        "4B"  # pp[4]

        # seen moves
        "4B"  # seen_move[4]

        # misc flags
        "B"  # ppBonuses
        "B"  # isEgg
        "B"  # gender
        "B"  # nature

        # EVs
        "6B"

        # IVs
        "6B"

        # Extra
        "B"  # seen
        "B"  # abilityNum
    )

    STRUCT_SIZE = struct.calcsize(POKE_STRUCT_FMT)

    def __init__(self, raw_bytes: bytes):
        if len(raw_bytes) != self.STRUCT_SIZE:
            raise ValueError(
                f"Invalid byte size. "
                f"Expected {self.STRUCT_SIZE}, got {len(raw_bytes)}"
            )

        u = struct.unpack(self.POKE_STRUCT_FMT, raw_bytes)

        i = 0

        self.species = u[i]
        i += 1

        self.attack = u[i]
        i += 1
        self.defense = u[i]
        i += 1
        self.speed = u[i]
        i += 1
        self.sp_attack = u[i]
        i += 1
        self.sp_defense = u[i]
        i += 1

        self.moves = list(u[i:i + 4])
        i += 4

        self.hp = u[i]
        i += 1
        self.max_hp = u[i]
        i += 1
        self.item = u[i]
        i += 1

        self.level = u[i]
        i += 1
        self.friendship = u[i]
        i += 1

        self.personality = u[i]
        i += 1

        self.status1 = u[i]
        i += 1
        self.status2 = u[i]
        i += 1

        self.stat_stages = list(u[i:i + 8])
        i += 8

        self.pps = list(u[i:i + 4])
        i += 4

        self.seen_moves = list(u[i:i + 4])
        i += 4

        self.pp_bonuses = u[i]
        i += 1
        self.is_egg = u[i]
        i += 1
        self.gender = u[i]
        i += 1
        self.nature = u[i]
        i += 1

        # EVs
        self.evs = {
            "hp": u[i + 0],
            "atk": u[i + 1],
            "def": u[i + 2],
            "spe": u[i + 3],
            "spa": u[i + 4],
            "spd": u[i + 5],
        }
        i += 6

        # IVs
        self.ivs = {
            "hp": u[i + 0],
            "atk": u[i + 1],
            "def": u[i + 2],
            "spe": u[i + 3],
            "spa": u[i + 4],
            "spd": u[i + 5],
        }
        i += 6
        self.ability_num = u[i]
        i += 1
        self.seen = u[i]

    def display(self):
        if DISPLAY_USE_NAMES:
            species_str = SPECIES_ID_TO_PS[self.species]
            ability_str = ABILITY_ID_TO_PS[self.ability_num]
            moves_str = " | ".join(
                f"{MOVE_ID_TO_PS[m]} (PP:{p})"
                for m, p in zip(self.moves, self.pps)
                if m != 0
            )
        else:
            species_str = str(self.species)
            ability_str = str(self.ability_num)
            moves_str = " | ".join(
                f"ID:{m} (PP:{p})"
                for m, p in zip(self.moves, self.pps)
                if m != 0
            )

        status_txt = (
            "Healthy"
            if self.status1 == 0
            else f"Condition Flags: {self.status1:08X}"
        )

        print(
            f"  ● Species:{species_str:<20} "
            f"[Lv.{self.level:<2}] "
            f"HP: {self.hp}/{self.max_hp} "
            f"({status_txt})"
        )

        print(
            f"    Stats: "
            f"Atk:{self.attack} "
            f"Def:{self.defense} "
            f"Spe:{self.speed} "
            f"SpA:{self.sp_attack} "
            f"SpD:{self.sp_defense}"
        )

        print(
            f"    Stats Stages: "
            f"Atk:{self.stat_stages[0]} "
            f"Def:{self.stat_stages[1]} "
            f"SpA:{self.stat_stages[2]} "
            f"Spe:{self.stat_stages[3]} "
            f"SpD:{self.stat_stages[4]} "
            f"Acc:{self.stat_stages[5]} "
        )

        print(f"    Moves: {moves_str}")
        print(f"    EVs: {self.evs}")
        print(f"    IVs: {self.ivs}")

        print(
            f"    Nature:{self.nature} "
            f"Friendship:{self.friendship} "
            f"Ability:{ability_str}"
        )

        print("-" * 65)


# -------------------------------------------------------------------------
# 2. API REQUEST & ENDPOINT DEFINITIONS
# -------------------------------------------------------------------------
class BattleStatePayload(BaseModel):
    player: List[str]  # List of hexadecimal strings sent from Lua
    enemy: List[str]

def read_until_sentinel(sentinels, max_lines=60):
    """Read lines from Showdown stdout until a sentinel tag is seen."""
    lines = []
    stopProcessing = False
    for _ in range(max_lines):
        line = showdown_proc.stdout.readline()
        if not line:
            break
        lines.append(line.rstrip())

        for sentinel in sentinels:
            if sentinel in line:
                stopProcessing = True
        if stopProcessing:
            break
    return lines

def start_showdown_battle(player_team, enemy_team):
    """
    Sends battle initialization commands to your persistent ps.js process.
    """

    # Convert into Showdown team objects
    p1_sets = [build_showdown_set(mon) for mon in player_team]
    p2_sets = [build_showdown_set(mon) for mon in enemy_team]

    # Start battle
    # print('>start {"formatid":"gen3ou"}\n')
    # print(f'>player p1 {json.dumps({"name": "AI", "team": p1_sets})}\n')
    # print(f'>player p2 {json.dumps({"name": "Enemy", "team": p2_sets})}\n')
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
    print(read_until_sentinel({"turn"}))
    # tell pokemon showdown to use attack move 1
    showdown_proc.stdin.write(">p1 move 1\n")
    showdown_proc.stdin.write(">p2 move 1\n")
    showdown_proc.stdin.flush()

    print(read_until_sentinel({"turn", "winner"}))
    # Return decision byte 0x01 = "use move 1"
    # time.sleep(5)
    return 0x00


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
        "nickname": species,
        "level": mon.level,

        "hp": mon.hp,
        "maxhp": mon.max_hp,

        "status": status,

        "moves": moves,

        "boosts": boosts,

        "evs": mon.evs,
        "ivs": mon.ivs,

        "nature": NATURES[mon.nature],

        "item": ITEM_ID_TO_PS.get(
            mon.item,
            ""
        ),
    }


def process_predict(payload: BattleStatePayload):
    print("\n" + "=" * 25 + " INCOMING BATTLE STATE " + "=" * 25)

    try:
        player_team = []
        enemy_team = []
        print("\n[YOUR PARTY]")
        print("-" * 65)
        for hex_str in payload.player:
            mon = BattlePokemon(bytes.fromhex(hex_str))
            mon.display()
            ps_mon = map_gba_to_ps(mon, species_id=mon.species)
            player_team.append(ps_mon)

        print("\n[ENEMY PARTY]")
        print("-" * 65)
        for hex_str in payload.enemy:
            mon = BattlePokemon(bytes.fromhex(hex_str))
            mon.display()
            ps_mon = map_gba_to_ps(mon, species_id=mon.species)
            enemy_team.append(ps_mon)

        # -----------------------------------------------------------------
        # START SHOWDOWN SIM
        # -----------------------------------------------------------------
        print("start_showdown_battle")
        decision_byte = 0x00
        try:
            decision_byte = start_showdown_battle(player_team, enemy_team)
        except Exception as e:
            print(e)

        print(f"Decision evaluated. Releasing GBA with: {decision_byte}")
        return decision_byte

    except Exception as e:
        print(f"Parsing error: {e}")


# GBA text encoding translation map (Gen 3 English mapping fallback helper)
GBA_CHAR_MAP = {i: chr(i - 0xBB + ord('A')) for i in range(0xBB, 0xD4)}  # A-Z
GBA_CHAR_MAP.update({i: chr(i - 0xD5 + ord('a')) for i in range(0xD5, 0xEE)})  # a-z
GBA_CHAR_MAP[0x00] = ""  # End of String
GBA_CHAR_MAP[0xFF] = " "
MOVE_ID_TO_PS = parse_c_defines(
    ROOT_DIR / "../pokeemerald/include/constants/moves.h",
    "MOVE_"
)

SPECIES_ID_TO_PS = parse_c_defines(
    ROOT_DIR / "../pokeemerald/include/constants/species.h",
    "SPECIES_"
)

ITEM_ID_TO_PS = parse_c_defines(
    ROOT_DIR / "../pokeemerald/include/constants/items.h",
    "ITEM_"
)

ABILITY_ID_TO_PS = parse_c_defines(
    ROOT_DIR / "../pokeemerald/include/constants/abilities.h",
    "ABILITY_"
)

if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8080

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"Listening on {HOST}:{PORT}")
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

    while True:
        conn, addr = server.accept()

        try:
            raw_data = conn.recv(65536).decode()

            payload = BattleStatePayload(
                **json.loads(raw_data)
            )

            # JUST CALL YOUR EXISTING FUNCTION
            decision_byte = process_predict(payload)

            conn.send(str(decision_byte).encode())
            print(str(decision_byte).encode())

        except Exception as e:
            print(e)

            try:
                conn.send(b"7")
            except:
                pass

        conn.close()
