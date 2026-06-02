"""
battle_evaluator.py

Owns the Pokemon Showdown subprocess and exposes a single entry point:

    predict(player_team, enemy_team) -> int

Both arguments are lists of Showdown-compatible dicts (as produced by
map_gba_to_ps / build_showdown_set in pokemon_battle_simulator.py).
Returns a decision byte (0x00 on success).
"""

import json
import subprocess
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Showdown subprocess — started once at import time
# ---------------------------------------------------------------------------

showdown_proc = subprocess.Popen(
    ["node", str(ROOT_DIR / "ps.js")],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
)
time.sleep(1)

if showdown_proc.poll() is None:
    print("[battle_evaluator] Showdown process is running.")
else:
    print(f"[battle_evaluator] Showdown process exited early "
          f"(code {showdown_proc.returncode})")
    print(showdown_proc.stderr.read())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_until_sentinel(sentinels: set[str], max_lines: int = 60) -> list[str]:
    """Read lines from Showdown stdout until any sentinel string appears."""
    lines = []
    stop = False
    for _ in range(max_lines):
        line = showdown_proc.stdout.readline()
        if not line:
            break
        lines.append(line.rstrip())
        if any(s in line for s in sentinels):
            stop = True
        if stop:
            break
    return lines


def _start_showdown_battle(player_sets: list[dict], enemy_sets: list[dict]) -> int:
    """
    Send both teams to the running Showdown process and simulate one turn.
    Returns 0x00 on completion.
    """
    showdown_proc.stdin.write('>start {"formatid":"gen3customgame"}\n')
    showdown_proc.stdin.write(
        f'>player p1 {json.dumps({"name": "AI", "team": player_sets})}\n'
    )
    showdown_proc.stdin.write(
        f'>player p2 {json.dumps({"name": "Enemy", "team": enemy_sets})}\n'
    )
    showdown_proc.stdin.flush()

    print("\n[SHOWDOWN OUTPUT]")
    print("-" * 65)
    print(_read_until_sentinel({"turn"}))

    showdown_proc.stdin.write(">p1 move 1\n")
    showdown_proc.stdin.write(">p2 move 1\n")
    showdown_proc.stdin.flush()

    print(_read_until_sentinel({"turn", "winner", "switch", "win", "faint"}))

    return 0x00


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def predict(player_team: list[dict], enemy_team: list[dict]) -> int:
    """
    Evaluate a battle state using Pokemon Showdown.

    Parameters
    ----------
    player_team : list[dict]
        Showdown-compatible set dicts for the player's active party.
    enemy_team : list[dict]
        Showdown-compatible set dicts for the enemy's active party.

    Returns
    -------
    int
        A decision byte. Currently always 0x00 on success.
    """
    try:
        decision_byte = _start_showdown_battle(player_team, enemy_team)
        print(f"[battle_evaluator] Decision: {decision_byte}")
        return decision_byte
    except Exception as exc:
        print(f"[battle_evaluator] Error during evaluation: {exc}")
        return 0x00