import struct
import socket
import json
from pydantic import BaseModel
from typing import List
import re
from pathlib import Path
from coordinator import search, ActionKind


DISPLAY_USE_NAMES = True  # Toggle: True = human-readable names, False = raw byte values

NATURES = [
    "Hardy", "Lonely", "Brave", "Adamant", "Naughty",
    "Bold", "Docile", "Relaxed", "Impish", "Lax",
    "Timid", "Hasty", "Serious", "Jolly", "Naive",
    "Modest", "Mild", "Quiet", "Bashful", "Rash",
    "Calm", "Gentle", "Sassy", "Careful", "Quirky",
]

ROOT_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# C-header translation helpers
# ---------------------------------------------------------------------------

def parse_c_defines(path, prefix):
    mapping = {}
    define_re = re.compile(rf"#define\s+{prefix}([A-Z0-9_]+)\s+(\d+)")
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            match = define_re.match(line.strip())
            if not match:
                continue
            name = match.group(1)
            value = int(match.group(2))
            if name == "COUNT":
                break
            ps_name = name.lower().replace("_", "")
            mapping[value] = ps_name
    return mapping


# GBA text encoding translation map (Gen 3 English mapping)
GBA_CHAR_MAP = {i: chr(i - 0xBB + ord("A")) for i in range(0xBB, 0xD4)}   # A–Z
GBA_CHAR_MAP.update({i: chr(i - 0xD5 + ord("a")) for i in range(0xD5, 0xEE)})  # a–z
GBA_CHAR_MAP[0x00] = ""    # End of string
GBA_CHAR_MAP[0xFF] = " "

MOVE_ID_TO_PS = parse_c_defines(
    ROOT_DIR / "../pokeemerald/include/constants/moves.h", "MOVE_"
)
SPECIES_ID_TO_PS = parse_c_defines(
    ROOT_DIR / "../pokeemerald/include/constants/species.h", "SPECIES_"
)
ITEM_ID_TO_PS = parse_c_defines(
    ROOT_DIR / "../pokeemerald/include/constants/items.h", "ITEM_"
)
ABILITY_ID_TO_PS = parse_c_defines(
    ROOT_DIR / "../pokeemerald/include/constants/abilities.h", "ABILITY_"
)


def decode_gba_string(raw_bytes: bytes) -> str:
    """Decodes raw GBA string buffers using the native character offsets."""
    decoded = []
    for b in raw_bytes:
        if b == 0xFF:
            break
        decoded.append(GBA_CHAR_MAP.get(b, f"[{b:02X}]"))
    return "".join(decoded).strip()


# ---------------------------------------------------------------------------
# GBA battle struct parser
# ---------------------------------------------------------------------------

class BattlePokemon:
    NUM_MOVES = 4
    NUM_STATS = 8

    POKE_STRUCT_FMT = (
        "<"   # little-endian
        "H"   # species
        "H"   # attack
        "H"   # defense
        "H"   # speed
        "H"   # spAttack
        "H"   # spDefense
        "4H"  # moves[4]
        "H"   # hp
        "H"   # maxHP
        "H"   # item
        "B"   # level
        "B"   # friendship
        "I"   # personality
        "I"   # status1
        "I"   # status2
        "8b"  # statStages[8]
        "4B"  # pp[4]
        "4B"  # seen_move[4]
        "B"   # ppBonuses
        "B"   # isEgg
        "B"   # gender
        "B"   # nature
        "6B"  # EVs
        "6B"  # IVs
        "B"   # seen
        "B"   # abilityNum
    )

    STRUCT_SIZE = struct.calcsize(POKE_STRUCT_FMT)

    def __init__(self, raw_bytes: bytes):
        if len(raw_bytes) != self.STRUCT_SIZE:
            raise ValueError(
                f"Invalid byte size. Expected {self.STRUCT_SIZE}, got {len(raw_bytes)}"
            )

        u = struct.unpack(self.POKE_STRUCT_FMT, raw_bytes)
        i = 0

        self.species    = u[i]; i += 1
        self.attack     = u[i]; i += 1
        self.defense    = u[i]; i += 1
        self.speed      = u[i]; i += 1
        self.sp_attack  = u[i]; i += 1
        self.sp_defense = u[i]; i += 1

        self.moves = list(u[i:i + 4]); i += 4

        self.hp       = u[i]; i += 1
        self.max_hp   = u[i]; i += 1
        self.item     = u[i]; i += 1
        self.level    = u[i]; i += 1
        self.friendship = u[i]; i += 1
        self.personality = u[i]; i += 1
        self.status1  = u[i]; i += 1
        self.status2  = u[i]; i += 1

        self.stat_stages = list(u[i:i + 8]); i += 8
        self.pps         = list(u[i:i + 4]); i += 4
        self.seen_moves  = list(u[i:i + 4]); i += 4

        self.pp_bonuses = u[i]; i += 1
        self.is_egg     = u[i]; i += 1
        self.gender     = u[i]; i += 1
        self.nature     = u[i]; i += 1

        self.evs = {
            "hp": u[i+0], "atk": u[i+1], "def": u[i+2],
            "spe": u[i+3], "spa": u[i+4], "spd": u[i+5],
        }; i += 6

        self.ivs = {
            "hp": u[i+0], "atk": u[i+1], "def": u[i+2],
            "spe": u[i+3], "spa": u[i+4], "spd": u[i+5],
        }; i += 6

        self.ability_num = u[i]; i += 1
        self.seen        = u[i]

    def display(self):
        if DISPLAY_USE_NAMES:
            species_str = SPECIES_ID_TO_PS[self.species]
            ability_str = ABILITY_ID_TO_PS[self.ability_num]
            moves_str = " | ".join(
                f"{MOVE_ID_TO_PS[m]} (PP:{p})"
                for m, p in zip(self.moves, self.pps) if m != 0
            )
        else:
            species_str = str(self.species)
            ability_str = str(self.ability_num)
            moves_str = " | ".join(
                f"ID:{m} (PP:{p})"
                for m, p in zip(self.moves, self.pps) if m != 0
            )

        status_txt = (
            "Healthy" if self.status1 == 0
            else f"Condition Flags: {self.status1:08X}"
        )

        print(
            f"  ● Species:{species_str:<20} "
            f"[Lv.{self.level:<2}] "
            f"HP: {self.hp}/{self.max_hp} ({status_txt})"
        )
        print(
            f"    Stats: "
            f"Atk:{self.attack} Def:{self.defense} Spe:{self.speed} "
            f"SpA:{self.sp_attack} SpD:{self.sp_defense}"
        )
        print(
            f"    Stats Stages: "
            f"Atk:{self.stat_stages[0]} Def:{self.stat_stages[1]} "
            f"SpA:{self.stat_stages[2]} Spe:{self.stat_stages[3]} "
            f"SpD:{self.stat_stages[4]} Acc:{self.stat_stages[5]}"
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


# ---------------------------------------------------------------------------
# GBA → Showdown translation
# ---------------------------------------------------------------------------

def map_gba_to_ps(mon: BattlePokemon, species_id: int) -> dict:
    """Converts a parsed GBA battle struct into a Showdown-compatible dict."""

    # Status
    if   mon.status1 & 0x7:  status = "slp"
    elif mon.status1 & 0x8:  status = "psn"
    elif mon.status1 & 0x10: status = "brn"
    elif mon.status1 & 0x20: status = "frz"
    elif mon.status1 & 0x40: status = "par"
    elif mon.status1 & 0x80: status = "tox"
    else:                    status = None

    moves = [
        MOVE_ID_TO_PS.get(mid, f"unknownmove{mid}")
        for mid in mon.moves if mid != 0
    ]

    boosts = {
        "atk":      mon.stat_stages[1],
        "def":      mon.stat_stages[2],
        "spe":      mon.stat_stages[3],
        "spa":      mon.stat_stages[4],
        "spd":      mon.stat_stages[5],
        "accuracy": mon.stat_stages[0],
        "evasion":  mon.stat_stages[6],
    }

    species = SPECIES_ID_TO_PS.get(species_id, f"unknownspecies{species_id}")

    return {
        "species":  species,
        "nickname": species,
        "level":    mon.level,
        "hp":       mon.hp,
        "maxhp":    mon.max_hp,
        "status":   status,
        "moves":    moves,
        "pps":      list(mon.pps),
        "boosts":   boosts,
        "evs":      mon.evs,
        "ivs":      mon.ivs,
        "nature":   NATURES[mon.nature],
        "item":     ITEM_ID_TO_PS.get(mon.item, ""),
    }


def build_showdown_set(mon_dict: dict) -> dict:
    return {
        "species":      mon_dict["species"].capitalize(),
        "name":         mon_dict.get("nickname", ""),
        "item":         mon_dict.get("item", ""),
        "ability":      "None",
        "moves":        mon_dict["moves"],
        "nature":       mon_dict.get("nature", "Hardy"),
        "evs":          mon_dict.get("evs", {"hp":0,"atk":0,"def":0,"spa":0,"spd":0,"spe":0}),
        "ivs":          mon_dict.get("ivs", {"hp":31,"atk":31,"def":31,"spa":31,"spd":31,"spe":31}),
        "level":        mon_dict["level"],
        "customHp":     mon_dict.get("hp", None),
        "customPp":     mon_dict.get("pps", None),
        "customStatus": mon_dict.get("status", ""),
    }


# ---------------------------------------------------------------------------
# Incoming payload model
# ---------------------------------------------------------------------------

class BattleStatePayload(BaseModel):
    player: List[str]   # hex strings from Lua
    enemy:  List[str]


# ---------------------------------------------------------------------------
# Main processing pipeline
# ---------------------------------------------------------------------------

def process_predict(payload: BattleStatePayload) -> int:
    print("\n" + "=" * 25 + " INCOMING BATTLE STATE " + "=" * 25)

    try:
        player_team, enemy_team = [], []

        print("\n[YOUR PARTY]")
        print("-" * 65)
        for hex_str in payload.player:
            mon = BattlePokemon(bytes.fromhex(hex_str))
            mon.display()
            player_team.append(build_showdown_set(map_gba_to_ps(mon, mon.species)))

        print("\n[ENEMY PARTY]")
        print("-" * 65)
        for hex_str in payload.enemy:
            mon = BattlePokemon(bytes.fromhex(hex_str))
            mon.display()
            enemy_team.append(build_showdown_set(map_gba_to_ps(mon, mon.species)))

        result = search(player_team, enemy_team, depth=2)
        action = result.best_action

        if action.kind == ActionKind.MOVE:
            # GBA move indices are 1-based (1–4).
            decision_byte = action.slot + 1
        else:
            # GBA switch indices: 5 + 1-based reserve slot (5=slot0, 6=slot1, …).
            decision_byte = 5 + action.slot

        print(f"Decision evaluated. {action} "
              f"(score {result.score:+.2f}). Releasing GBA with: {decision_byte}")
        return decision_byte

    except Exception as e:
        print(f"Parsing error: {e}")
        return 0x00


# ---------------------------------------------------------------------------
# Socket server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 8080

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"Listening on {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        try:
            raw_data = conn.recv(65536).decode()
            payload = BattleStatePayload(**json.loads(raw_data))
            decision_byte = process_predict(payload)
            conn.send(str(decision_byte).encode())
            print(str(decision_byte).encode())
        except Exception as exc:
            print(exc)
            try:
                conn.send(b"7")
            except Exception as catastrophic:
                print(catastrophic)
                exit(1)
        conn.close()
