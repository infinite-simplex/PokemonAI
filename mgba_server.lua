local FLAG_ADDRESS = 0x2ffffff
local DATA_START_ADDRESS = 0x3000100

local SERVER_IP = "127.0.0.1"
local SERVER_PORT = 8080
local STRUCT_SIZE = 74 --bytes
local PADDING_SIZE = 6 -- bytes


local function parsePokemonBlock(address)
    local hexStr = ""
    -- Read the full structural block for one Pokemon
    for i = 0, STRUCT_SIZE-1 do
        local byte = emu:read8(address + i)
        hexStr = hexStr .. string.format("%02X", byte)
    end
    return hexStr
end

local function handleBattleTurn()
    -- Read your signaling flag
    local flag = emu:read8(FLAG_ADDRESS)
    
    if flag == 0xFE then
        console:log("AI Choice requested. Scraping battle memory at")
        console:log(string.format("%02X", DATA_START_ADDRESS))
        
        local player_team = {}
        local enemy_team = {}
        local current_address = DATA_START_ADDRESS
        
        -- Read up to 12 pokemon blocks
        for i = 1, 12 do
            local parsed_pokemon = parsePokemonBlock(current_address)
			local team_marker = string.sub(parsed_pokemon, (STRUCT_SIZE-1)*2 + 1, STRUCT_SIZE*2)

			console:log(team_marker)
			if team_marker == "AA" then
				table.insert(player_team, parsed_pokemon)
			elseif team_marker == "BB" then
				table.insert(enemy_team, parsed_pokemon)
			else
                break
            end

            current_address = current_address + STRUCT_SIZE + PADDING_SIZE
        end


        -- Format payload
        local payload = string.format(
            '{"player":[%s],"enemy":[%s]}',
            '"' .. table.concat(player_team, '","') .. '"',
            '"' .. table.concat(enemy_team, '","') .. '"'
        )
        local start_time = os.clock()
        console:log(payload)
        -- Send data to simulation server
        local client = socket.tcp()
        if client:connect(SERVER_IP, SERVER_PORT) then
            -- send body AFTER blank line
            client:send(payload)

            local response, err
            local attempts = 0

            repeat
                client:poll()
                response, err = client:receive(1)
                attempts = attempts + 1
            until response ~= nil or (os.clock() - start_time) > 10

            console:log("RESPONSE: " .. tostring(response))
            console:log("ERR: " .. tostring(err))

            client:close()

            local decisionByte = tonumber(response) or 0x07

            emu:write8(FLAG_ADDRESS, decisionByte)

            console:log(
                "Decision byte written: " ..
                string.format("0x%02X", decisionByte)
            )
        else
            console:log("Connection failed.")
        end
    end
end

-- Check every frame for the flag change
callbacks:add("frame", handleBattleTurn)
