local FLAG_ADDRESS = 0x2ffffff
local DATA_START_ADDRESS = 0x3000100

local SERVER_IP = "127.0.0.1"
local SERVER_PORT = 8080

local function parsePokemonBlock(address)
    local hexStr = ""
    -- Read the full 48-byte (0x30) structural block for one Pokemon
    for i = 0, 47 do
        local byte = emu:read8(address + i)
        hexStr = hexStr .. string.format("%02X", byte)
    end
    return hexStr
end

local function handleBattleTurn()
    -- Read your signaling flag
    local flag = emu:read8(FLAG_ADDRESS)
    
    if flag == 0xFE then
        console:log("AI Choice requested. Scraping battle memory...")
        
        local player_team = {}
        local enemy_team = {}
        local current_address = DATA_START_ADDRESS
        
        -- Loop through a potential maximum party size of 6 for Player
        for i = 1, 6 do
            local marker = emu:read8(current_address + 0x0A)
            if marker ~= 0xAA then break end -- Break if no more active player mons
            table.insert(player_team, parsePokemonBlock(current_address))
            current_address = current_address + 0x30
        end
        
        -- Loop through a potential maximum party size of 6 for Enemy
        for i = 1, 6 do
            local marker = emu:read8(current_address + 0x0A)
            if marker ~= 0xBB then break end -- Break if no more active enemy mons
            table.insert(enemy_team, parsePokemonBlock(current_address))
            current_address = current_address + 0x30
        end
        
        -- Format payload
        local payload = string.format(
            '{"player":[%s],"enemy":[%s]}',
            '"' .. table.concat(player_team, '","') .. '"',
            '"' .. table.concat(enemy_team, '","') .. '"'
        )
        
        -- Send data to simulation server
        local client = socket.tcp()
        
        if client:connect(SERVER_IP, SERVER_PORT) then
            client:send("POST /predict HTTP/1.1\r\n")
            client:send("Host: localhost\r\n")
            client:send("Content-Type: application/json\r\n")
            client:send("Content-Length: " .. string.len(payload) .. "\r\n\r\n")
            client:send(payload)
            
            -- Read the decision response from your server
            local response, err = client:receive("*l") -- Expects a single text line response
            client:close()
            
            if response then
                -- Parse your decision byte from server text response (e.g., "0x10" or "0x01")
                local decisionByte = tonumber(response) or 0x00
                
                -- Write back choice to release the C game loop freeze
                emu:write8(FLAG_ADDRESS, decisionByte) 
                console:log("Decision byte written back to ROM: " .. string.format("0x%02X", decisionByte))
            end
        else
            console:error("Failed to connect to calculation server.")
            emu:write8(FLAG_ADDRESS, 0x00) -- Fallback safety break
        end
    end
end

-- Check every frame for the flag change
callbacks:add("frame", handleBattleTurn)
