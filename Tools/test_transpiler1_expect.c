void test(void)
{
    int z;
    int f;
    int x;
    int i;
    z = 0;
    z++;
    f = -1;
    x = 3;

    for (i = 0; i < 10; i++)
    {
        int q;
        q = i;
    }
}

void test2(void)
{
    int z;
    int f;
    int x;
    int i;
    z = 0;
    z++;
    f = -1;
    x = 3;

    for (i = 0; i < 10; i++)
    {
        int q;
        q = i;
    }
}

static const u8 sTargetIdentities[MAX_BATTLERS_COUNT] = { B_POSITION_PLAYER_LEFT, B_POSITION_PLAYER_RIGHT, B_POSITION_OPPONENT_RIGHT, B_POSITION_OPPONENT_LEFT };

static void HandleInputChooseAction(void)
{
    u16 itemId;
    u8* base;
    u8* base_2;
    u8 j;
    itemId = gBattleBufferA[gActiveBattler][2] | (gBattleBufferA[gActiveBattler][3] << 8);
    base = (u8*)0x3000100;
    base_2 = (u8*)0x2ffffff;
    *base_2 = 0xfe;
    j = 1;

    base = dumpPlayerMons(base);
    base = dumpEnemyMons(base);
    *(base) = 0xff;
}

static void dumpMemoryOfPokemon(u8* base, struct BattlePokemon* toDump) {
    s32 i;
    u8* str_nickname;
    u8* seen;
    u8* level;
    u32* status1;
    u32* status2;
    u16* moves;
    u8* seen_move;
    u8* pps;
    u8* stat_changes;
    u16* hp;
    u16* maxHP;
    // 0x00
    str_nickname = base; // 10 bytes
    // 0x0A
    seen = (u8*)(base + 0xA);
    // 0x0B
    level = (u8*)(base + 0xB);
    // 0x0C
    status1 = (u32*)(base + 0xC);
    // 0x10
    status2 = (u32*)(base + 0x10);
    // 0x14
    moves = (u16*)(base + 0x14); // 4 * u16 = 8 bytes
    // 0x1C
    seen_move = (u8*)(base + 0x1C); // 4 bytes
    // 0x20
    pps = (u8*)(base + 0x20); // 4 bytes
    // 0x24
    stat_changes = (u8*)(base + 0x24); // 8 bytes
    // 0x2C
    hp = (u16*)(base + 0x2C);
    // 0x2E
    maxHP = (u16*)(base + 0x2E);

    for (i = 0; i < POKEMON_NAME_LENGTH; i++) {
        *(str_nickname + i) = toDump->nickname[i];
    }
    for (i = 0; i < MAX_MON_MOVES; i++) {
        *(moves + i) = toDump->moves[i];
        *(seen_move + i) = toDump->seen_move[i];
        *(pps + i) = toDump->pp[i];
    }
    for (i = 0; i < NUM_BATTLE_STATS - 1; i++) {
        *(stat_changes + i + 1) = toDump->statStages[i + 1];
    }
    *hp = toDump->hp;
    *maxHP = toDump->maxHP;
    *level = toDump->level;
    *status1 = toDump->status1;
    *status2 = toDump->status2;
    *seen = toDump->seen;
}

u8* dumpPlayerMons(u8* base) {
    s32 i;
    s32 j;
    u8 count;
    struct BattlePokemon playerMons[6];
    count = CalculatePlayerPartyCount();
    //fill in our data
    for (i = 0; i < count; i++) {
        struct BattlePokemon* bp;
        bp = &playerMons[i];
        GetMonData(&gPlayerParty[i], MON_DATA_NICKNAME, bp->nickname);
        if (bp->nickname == 0) {
            break;
        }

        bp->hp = GetMonData(&gPlayerParty[i], MON_DATA_HP);
        bp->maxHP = GetMonData(&gPlayerParty[i], MON_DATA_MAX_HP);
        bp->level = GetMonData(&gPlayerParty[i], MON_DATA_LEVEL);
        // DebugPrintf("%S", bp->nickname);
        // DebugPrintf("%u", bp->hp);
        // DebugPrintf("%u", bp->maxHP);
        // DebugPrintf("%u", bp->level);
        // DebugPrintf("END OF POKEMON");
        for (j = 0; j < MAX_MON_MOVES; j++) {
            bp->moves[j] = GetMonData(&gPlayerParty[i], MON_DATA_MOVE1 + j);
            if (bp->moves[j] == 0) {
                bp->pp[j] = 0xdf;
                bp->seen_move[j] = 0xf;
            }
            else {
                bp->pp[j] = GetMonData(&gPlayerParty[i], MON_DATA_PP1 + j);
                bp->seen_move[j] = 0x1;
            }
        }
        for (j = 0; j < NUM_BATTLE_STATS; j++) {
            bp->statStages[j] = gBattleMons[i].statStages[j];
        }
        bp->seen = 0xaa;
    }

    for (i = 0; i < count; i++) {
        dumpMemoryOfPokemon(base, &playerMons[i]);
        base += 0x30;
    }
    return base;
}
