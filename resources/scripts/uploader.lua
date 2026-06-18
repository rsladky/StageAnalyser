-- uploader.lua — envoie le JSON d'une run à Supabase via la fonction RPC import_run.
--
-- Le Lua d'Isaac est sandboxé : l'accès réseau/fichier n'existe QUE si le jeu est
-- lancé avec le flag --luadebug. Comme socket.lua ne gère pas le HTTPS, on passe par
-- curl. L'interpréteur de commandes d'Isaac n'arrive pas à parser une longue commande
-- pleine de guillemets passée à io.popen ; on écrit donc la commande dans un .bat et on
-- exécute juste le .bat (un seul token). curl écrit sa réponse dans un fichier qu'on relit.

local Uploader = {}

-- Configuration Supabase (clé ANON publique — insert-only via RLS, sans danger).
local SUPABASE_URL = "https://xbhbdzsqxilwfigxdnuq.supabase.co"
local SUPABASE_ANON_KEY =
	"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhiaGJkenNxeGlsd2ZpZ3hkbnVxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkzOTYzNDgsImV4cCI6MjA4NDk3MjM0OH0.DASpyqZMkNWSbMTYn6_CyA8rWzbJMeAYfnlABL97RPs"

-- isaac-ng.exe est 32 bits : référencer System32 serait redirigé vers SysWOW64 par WoW64.
-- On essaie plusieurs emplacements dans l'ordre :
--   1. C:\curl\curl.exe          -- dossier dédié non redirigé (recommandé)
--   2. C:\Windows\Sysnative\...  -- depuis un process 32-bit, Sysnative pointe vers le vrai
--                                   System32 64-bit où curl est livré sur Win10/11
--   3. curl.exe                  -- fallback via le PATH système
local CURL_CANDIDATES = {
	"C:\\curl\\curl.exe",
	"C:\\Windows\\Sysnative\\curl.exe",
	"curl.exe",
}

local function log(msg)
	Isaac.DebugString("[StageAnalyser][Uploader] " .. tostring(msg))
end

-- Renvoie le premier chemin curl existant, ou "curl.exe" (PATH) si aucun fichier détecté.
local function findCurl()
	for _, path in ipairs(CURL_CANDIDATES) do
		-- "curl.exe" (PATH) n'est pas vérifiable via io.open : on le garde en dernier recours.
		if path == "curl.exe" then
			return path, false
		end
		local f = io.open(path, "r")
		if f then
			f:close()
			return path, true
		end
	end
	return "curl.exe", false
end

-- Le sandbox est-il levé ? (io/os disponibles seulement avec --luadebug)
local function luadebugAvailable()
	return io ~= nil and os ~= nil and os.execute ~= nil
end

local function writeFile(path, content)
	local f = io.open(path, "w")
	if not f then
		return false
	end
	f:write(content)
	f:close()
	return true
end

local function readFile(path)
	local f = io.open(path, "r")
	if not f then
		return nil
	end
	local s = f:read("*a")
	f:close()
	return s
end

-- Envoie le JSON d'une run. `jsonString` = l'objet run encodé.
function Uploader.Upload(jsonString)
	if not luadebugAvailable() then
		log("--luadebug désactivé : upload ignoré (io/os indisponibles).")
		return false
	end

	local ok, err = pcall(function()
		local dir = os.getenv("TEMP") or os.getenv("TMP") or "C:\\users\\crossover\\Temp"
		local payload = dir .. "\\stageanalyser_payload.json"
		local batf = dir .. "\\stageanalyser_upload.bat"
		local respf = dir .. "\\stageanalyser_response.txt"

		-- PostgREST RPC attend le corps { "payload": <run> } (nom de l'argument SQL).
		local body = '{"payload":' .. jsonString .. "}"
		if not writeFile(payload, body) then
			log("Échec écriture payload: " .. payload)
			return
		end
		log(string.format("Payload écrit: %s (%d octets)", payload, #body))

		local curl, found = findCurl()
		if found then
			log("curl: " .. curl)
		else
			log("curl introuvable aux emplacements connus — tentative via le PATH (curl.exe). "
				.. "Si l'upload échoue, placez curl.exe dans C:\\curl\\.")
		end

		-- Commande curl dans un .bat (%% → % dans un batch ; > redirige la réponse).
		local bat = table.concat({
			"@echo off",
			curl
				.. ' -sS -X POST "' .. SUPABASE_URL .. '/rest/v1/rpc/import_run"'
				.. ' -H "apikey: ' .. SUPABASE_ANON_KEY .. '"'
				.. ' -H "Authorization: Bearer ' .. SUPABASE_ANON_KEY .. '"'
				.. ' -H "Content-Type: application/json"'
				.. ' --data-binary "@' .. payload .. '"'
				.. ' -w "[HTTP %%{http_code}]"'
				.. ' > "' .. respf .. '" 2>&1',
		}, "\r\n")

		if not writeFile(batf, bat) then
			log("Échec écriture bat: " .. batf)
			return
		end

		os.remove(respf)
		-- Exécuter le .bat (un seul token entre guillemets → pas de souci de parsing).
		os.execute('"' .. batf .. '"')

		local response = readFile(respf)
		log("curl -> " .. (response and response ~= "" and response or "(pas de réponse)"))

		-- curl ajoute "[HTTP <code>]" en fin de réponse (-w). Une réponse vide ou un code
		-- non-2xx = échec : on l'annonce clairement plutôt que de laisser croire à un succès.
		if not response or response == "" then
			log("ÉCHEC : aucune réponse de curl (binaire introuvable ou non exécuté ?).")
		elseif not response:find("%[HTTP 2") then
			log("ÉCHEC : réponse HTTP non-2xx — la run n'a probablement PAS été enregistrée.")
		end

		os.remove(payload)
		os.remove(batf)
		os.remove(respf)
	end)

	if not ok then
		log("Erreur upload: " .. tostring(err))
		return false
	end
	return true
end

return Uploader
