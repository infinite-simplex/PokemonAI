"""
coordinator.py

Drives game tree traversal for Pokemon battle decision-making.

Entry point:
    result = search(player_team, enemy_team, depth)

Actions are typed (Move or Switch) so the two action types are never
conflated. Switches resolve before moves in Gen 3, encoded in the action
type for when simulate_turn becomes real.

Faint handling:
  - A fully wiped team is a hard terminal — scored immediately without
    recursing, depth is not decremented.
  - A mid-turn faint (active mon hp == 0 after simulate_turn) triggers a
    forced-switch ply that does NOT decrement depth, preserving the
    semantics of depth as "number of real turns looked ahead".

At depth == 0, leaves are scored by evaluate_leaf(), currently a stub.
Opponent moves are assumed to be all 4 move slots + all legal switch slots
(worst-case full grid).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
import copy


# ---------------------------------------------------------------------------
# Action types
# ---------------------------------------------------------------------------

class ActionKind(Enum):
    MOVE   = auto()
    SWITCH = auto()


@dataclass(frozen=True)
class Action:
    """
    A single player action for one turn.

    kind : ActionKind
        MOVE   — use a move from the active Pokemon's moveset.
        SWITCH — swap the active Pokemon for a reserve.

    slot : int
        MOVE   → 0-based index into active Pokemon's moves list (0–3).
        SWITCH → 0-based index into the RESERVE portion of the team list,
                 i.e. team[1] = slot 0, team[2] = slot 1, … team[5] = slot 4.
                 (team[0] is always the active mon, so slot 0 here = team[1].)
    """
    kind: ActionKind
    slot: int

    def __str__(self) -> str:
        if self.kind == ActionKind.MOVE:
            return f"Move({self.slot})"
        return f"Switch({self.slot})"


# Convenience constructors
def Move(slot: int)   -> Action: return Action(ActionKind.MOVE,   slot)
def Switch(slot: int) -> Action: return Action(ActionKind.SWITCH, slot)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """Outcome of search(): best action, its minimax score, root payoff matrix."""
    best_action: Action
    score: float
    # Rows = player actions, cols = opponent actions, in the same order as
    # available_actions() returns them. Kept for opponent prediction later.
    payoff_matrix: list[list[float]] = field(default_factory=list)
    player_actions: list[Action]     = field(default_factory=list)
    opponent_actions: list[Action]   = field(default_factory=list)


# ---------------------------------------------------------------------------
# Terminal state helpers
# ---------------------------------------------------------------------------

# Scores for hard terminal states — large enough to dominate any
# evaluate_leaf() heuristic, preserving correct minimax ordering.
WIN_SCORE  =  1_000_000.0
LOSS_SCORE = -1_000_000.0


def _is_wiped(team: list[dict]) -> bool:
    """True if every Pokemon on the team has fainted (hp == 0)."""
    return all(mon.get("hp", 0) == 0 for mon in team)


def _active_fainted(team: list[dict]) -> bool:
    """True if the active (index 0) Pokemon has fainted."""
    return team[0].get("hp", 0) == 0


# ---------------------------------------------------------------------------
# Action generation
# ---------------------------------------------------------------------------

def _alive_reserves(team: list[dict]) -> list[int]:
    """
    Return 0-based reserve indices (into team[1:]) for non-fainted Pokemon.
    A mon is considered fainted if hp == 0.
    """
    return [
        i for i, mon in enumerate(team[1:])
        if mon.get("hp", 0) > 0
    ]


def available_actions(team: list[dict]) -> list[Action]:
    """
    Return every legal action for the active (first) Pokemon's controller.

    Includes:
      - Move(slot) for each non-empty, non-zero-PP move slot (0–3).
      - Switch(slot) for each non-fainted reserve (team indices 1–5).

    If the active mon has no usable moves (e.g. all PP spent), Struggle
    is the real fallback — represented here as Move(0) so the tree always
    has at least one action.
    """
    active = team[0]
    actions: list[Action] = []

    # --- moves ---
    for i, move in enumerate(active.get("moves", [])):
        pp     = active.get("pps", [0, 0, 0, 0])
        pp_val = pp[i] if i < len(pp) else 0
        if move and pp_val > 0:
            actions.append(Move(i))

    if not any(a.kind == ActionKind.MOVE for a in actions):
        actions.append(Move(0))  # Struggle fallback

    # --- switches ---
    for reserve_idx in _alive_reserves(team):
        actions.append(Switch(reserve_idx))

    return actions


def _forced_switch_actions(team: list[dict]) -> list[Action]:
    """
    Actions available when the active mon has fainted and the player MUST
    switch. Only Switch actions to alive reserves are legal; no moves.
    Returns an empty list if the team is fully wiped (handled as terminal
    before this is called).
    """
    return [Switch(i) for i in _alive_reserves(team)]


def opponent_actions(enemy_team: list[dict]) -> list[Action]:
    """
    Return assumed opponent actions (worst-case full grid).

    Always includes all 4 move slots regardless of known PP, plus switches
    to any visible non-fainted reserve. Replace with filtered /
    probability-weighted list when opponent prediction is implemented.
    """
    actions: list[Action] = [Move(i) for i in range(4)]
    for reserve_idx in _alive_reserves(enemy_team):
        actions.append(Switch(reserve_idx))
    return actions


# ---------------------------------------------------------------------------
# State simulation stub
# ---------------------------------------------------------------------------

def simulate_turn(
    player_team:   list[dict],
    enemy_team:    list[dict],
    player_action: Action,
    enemy_action:  Action,
) -> tuple[list[dict], list[dict]]:
    """
    Advance the battle state by one turn given an action pairing.

    Switches resolve before moves (Gen 3 rule). This stub deep-copies the
    state and returns it unchanged (aside from switch rotation) so the tree
    can be exercised without a live Showdown process.

    TODO: call battle_evaluator to simulate a single turn in Showdown and
    deserialise the resulting state snapshot. The returned dicts must have
    updated hp values so faint detection works correctly.
    """
    new_player = copy.deepcopy(player_team)
    new_enemy  = copy.deepcopy(enemy_team)

    # Stub: apply switch rotation so branches are distinguishable.
    if player_action.kind == ActionKind.SWITCH:
        reserve_idx = player_action.slot + 1
        if reserve_idx < len(new_player):
            new_player[0], new_player[reserve_idx] = (
                new_player[reserve_idx], new_player[0]
            )

    if enemy_action.kind == ActionKind.SWITCH:
        reserve_idx = enemy_action.slot + 1
        if reserve_idx < len(new_enemy):
            new_enemy[0], new_enemy[reserve_idx] = (
                new_enemy[reserve_idx], new_enemy[0]
            )

    return new_player, new_enemy


def simulate_forced_switch(
    team:   list[dict],
    action: Action,
) -> list[dict]:
    """
    Apply a forced post-faint switch to a single team.

    Does not advance the turn counter — a forced switch after a faint is
    a free action in Gen 3, not a real turn.

    TODO: deserialise from Showdown once simulate_turn is real.
    """
    new_team = copy.deepcopy(team)
    reserve_idx = action.slot + 1
    if reserve_idx < len(new_team):
        new_team[0], new_team[reserve_idx] = new_team[reserve_idx], new_team[0]
    return new_team


# ---------------------------------------------------------------------------
# Leaf evaluation stub
# ---------------------------------------------------------------------------

def evaluate_leaf(player_team: list[dict], enemy_team: list[dict]) -> float:
    """
    Score a non-terminal leaf state from the player's perspective.

    Positive → favourable for player. Negative → favourable for opponent.

    Stub returns 0.0. Replace with battle_evaluator.predict() when ready.
    """
    # TODO: replace with battle_evaluator.predict(player_team, enemy_team)
    return 0.0


# ---------------------------------------------------------------------------
# Core minimax (maximin for simultaneous moves)
# ---------------------------------------------------------------------------

def _minimax(
    player_team: list[dict],
    enemy_team:  list[dict],
    depth: int,
    _ply: int = 0,
) -> float:
    """
    Recursive maximin over a simultaneous-move game tree.

    Standard alpha-beta cannot be used when both players choose at the same
    time. Instead we build the full N×M payoff matrix at each node and apply
    maximin: take the worst-case opponent response per player action, then
    pick the player action that maximises that worst case.

    Terminal conditions (checked before depth, so they always fire):
      1. Player team fully wiped  → LOSS_SCORE
      2. Enemy team fully wiped   → WIN_SCORE
      3. depth == 0               → evaluate_leaf()

    Faint-after-turn handling (does NOT decrement depth):
      - If the player's active mon faints after simulate_turn, we insert a
        forced-switch ply: enumerate all alive reserves as Switch actions,
        pick the one that maximises the subsequent minimax value, and
        recurse at the same depth.
      - Same logic for the enemy side (opponent forced to pick best switch
        from their perspective, i.e. the one that minimises our score —
        handled by taking min over their forced switches).
      - Both sides can faint simultaneously; both forced switches apply.
    """

    # --- hard terminals (team fully wiped) ---
    if _is_wiped(player_team):
        return LOSS_SCORE
    if _is_wiped(enemy_team):
        return WIN_SCORE

    # --- depth limit ---
    if depth == 0:
        return evaluate_leaf(player_team, enemy_team)

    p_actions = available_actions(player_team)
    o_actions = opponent_actions(enemy_team)

    worst_per_player: list[float] = []

    for p_act in p_actions:
        row_scores: list[float] = []
        for o_act in o_actions:
            next_p, next_e = simulate_turn(
                player_team, enemy_team, p_act, o_act
            )

            # --- faint detection & forced switches ---
            p_fainted = _active_fainted(next_p)
            e_fainted = _active_fainted(next_e)

            if p_fainted and not _is_wiped(next_p):
                # Player must switch — pick the switch that maximises score.
                forced = _forced_switch_actions(next_p)
                best_after_switch = max(
                    _minimax(simulate_forced_switch(next_p, sw), next_e,
                             depth, _ply + 1)   # depth unchanged — free action
                    for sw in forced
                )
                # Enemy may also have fainted simultaneously.
                if e_fainted and not _is_wiped(next_e):
                    e_forced = _forced_switch_actions(next_e)
                    # Opponent picks their best switch (minimises our score).
                    value = min(
                        _minimax(simulate_forced_switch(next_p, sw_p),
                                 simulate_forced_switch(next_e, sw_e),
                                 depth, _ply + 1)
                        for sw_p in forced
                        for sw_e in e_forced
                    )
                else:
                    value = best_after_switch

            elif e_fainted and not _is_wiped(next_e):
                # Only enemy active fainted — opponent picks best forced switch.
                e_forced = _forced_switch_actions(next_e)
                value = min(
                    _minimax(next_p, simulate_forced_switch(next_e, sw),
                             depth, _ply + 1)
                    for sw in e_forced
                )

            else:
                # No mid-turn faints — normal recursion.
                value = _minimax(next_p, next_e, depth - 1, _ply + 1)

            row_scores.append(value)
        worst_per_player.append(min(row_scores))

    return max(worst_per_player)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def search(
    player_team: list[dict],
    enemy_team:  list[dict],
    depth: int = 2,
) -> SearchResult:
    """
    Search the game tree and return the best action for the player.

    Parameters
    ----------
    player_team : list[dict]
        Showdown-compatible dicts, active mon at index 0, reserves at 1–5.
    enemy_team : list[dict]
        Same layout for the enemy.
    depth : int
        Turn lookahead. Default 2 per the paper's game-tree-pathology finding.

    Returns
    -------
    SearchResult
        Best action (Move or Switch), its minimax score, and the root
        payoff matrix with the action lists used to index it.
    """
    # Hard terminals at the root — shouldn't happen in practice but safe to check.
    if _is_wiped(player_team):
        dummy = Switch(0) if _alive_reserves(player_team) else Move(0)
        return SearchResult(best_action=dummy, score=LOSS_SCORE)
    if _is_wiped(enemy_team):
        return SearchResult(best_action=Move(0), score=WIN_SCORE)

    p_actions = available_actions(player_team)
    o_actions = opponent_actions(enemy_team)

    matrix: list[list[float]] = []

    for p_act in p_actions:
        row: list[float] = []
        for o_act in o_actions:
            next_p, next_e = simulate_turn(
                player_team, enemy_team, p_act, o_act
            )

            p_fainted = _active_fainted(next_p)
            e_fainted = _active_fainted(next_e)

            if p_fainted and not _is_wiped(next_p):
                forced = _forced_switch_actions(next_p)
                if e_fainted and not _is_wiped(next_e):
                    e_forced = _forced_switch_actions(next_e)
                    value = min(
                        _minimax(simulate_forced_switch(next_p, sw_p),
                                 simulate_forced_switch(next_e, sw_e),
                                 depth, _ply=1)
                        for sw_p in forced
                        for sw_e in e_forced
                    )
                else:
                    value = max(
                        _minimax(simulate_forced_switch(next_p, sw), next_e,
                                 depth, _ply=1)
                        for sw in forced
                    )
            elif e_fainted and not _is_wiped(next_e):
                e_forced = _forced_switch_actions(next_e)
                value = min(
                    _minimax(next_p, simulate_forced_switch(next_e, sw),
                             depth, _ply=1)
                    for sw in e_forced
                )
            else:
                value = _minimax(next_p, next_e, depth - 1, _ply=1)

            row.append(value)
        matrix.append(row)

    worst_per_player = [min(row) for row in matrix]
    best_value       = max(worst_per_player)
    best_idx         = worst_per_player.index(best_value)
    best_action      = p_actions[best_idx]

    _log_tree(p_actions, o_actions, matrix, best_action, best_value)

    return SearchResult(
        best_action=best_action,
        score=best_value,
        payoff_matrix=matrix,
        player_actions=p_actions,
        opponent_actions=o_actions,
    )


# ---------------------------------------------------------------------------
# Debug logging
# ---------------------------------------------------------------------------

def _log_tree(
    p_actions: list[Action],
    o_actions: list[Action],
    matrix:    list[list[float]],
    best:      Action,
    best_val:  float,
) -> None:
    col_w = 9
    print("\n[coordinator] Root payoff matrix (rows=player, cols=opponent)")
    header = "           " + "".join(f"{str(o):<{col_w}}" for o in o_actions)
    print(header)
    for p_act, row in zip(p_actions, matrix):
        marker  = " <--" if p_act == best else ""
        row_str = "".join(f"{v:+.2f}   " for v in row)
        print(f"  {str(p_act):<10}{row_str}{marker}")
    print(f"[coordinator] Best action: {best}  value: {best_val:+.2f}\n")


# ---------------------------------------------------------------------------
# Smoke tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    def _fake_mon(name: str, moves: list[str], hp: int = 100) -> dict:
        return {
            "species": name,
            "level":   50,
            "hp":      hp,
            "maxhp":   100,
            "moves":   moves,
            "pps":     [10, 10, 10, 10],
            "status":  None,
            "boosts":  {},
            "evs":     {},
            "ivs":     {},
            "nature":  "Hardy",
            "item":    "",
        }

    print("=" * 60)
    print("TEST 1 — normal battle, no faints")
    print("=" * 60)
    player_team = [
        _fake_mon("charizard", ["flamethrower", "airslash", "focusblast", "roost"]),
        _fake_mon("blissey",   ["softboiled", "thunderwave", "seismictoss", "protect"]),
        _fake_mon("garchomp",  ["earthquake", "dragonclaw", "swordsdance", "substitute"]),
    ]
    enemy_team = [
        _fake_mon("blastoise", ["surf", "icebeam", "flashcannon", "protect"]),
        _fake_mon("tyranitar", ["rockblast", "crunch", "earthquake", "dragondance"]),
        _fake_mon("fainted",   ["tackle"], hp=0),
    ]
    result = search(player_team, enemy_team, depth=2)
    print(f"Best action : {result.best_action}  score: {result.score:+.2f}")
    print(f"Player actions: {[str(a) for a in result.player_actions]}")

    print()
    print("=" * 60)
    print("TEST 2 — player active mon already fainted (forced switch at root)")
    print("=" * 60)
    fainted_lead = copy.deepcopy(player_team)
    fainted_lead[0]["hp"] = 0
    result2 = search(fainted_lead, enemy_team, depth=2)
    print(f"Best action : {result2.best_action}  score: {result2.score:+.2f}")

    print()
    print("=" * 60)
    print("TEST 3 — player team fully wiped (hard terminal at root)")
    print("=" * 60)
    wiped_team = [_fake_mon(n, ["tackle"], hp=0) for n in ["a", "b", "c"]]
    result3 = search(wiped_team, enemy_team, depth=2)
    print(f"Best action : {result3.best_action}  score: {result3.score:+.2f}")
