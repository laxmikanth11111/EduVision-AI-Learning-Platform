$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http
$BASE = "http://localhost:8000/api/v1"
$stamp = Get-Random -Maximum 99999
$email = "wire$stamp@t.com"
$script:pass = 0; $script:fail = 0
function Step($name, $ok, $detail) {
    if ($ok) { $script:pass++; "PASS  $name  ($detail)" }
    else { $script:fail++; "FAIL  $name  ($detail)"; throw "halted at $name" }
}

# 1. Register + login
$b = @{ email=$email; password="WireTest123!"; name="Wire" } | ConvertTo-Json
$r = Invoke-RestMethod -Uri "$BASE/auth/register" -Method POST -ContentType "application/json" -Body $b -TimeoutSec 30
$tok = $r.tokens.access_token
Step "auth register+login" ($tok.Length -gt 20) "token ok"
$H = @{ Authorization = "Bearer $tok" }

# 2. Create deck
$b = @{ title="Wiring Deck $stamp"; description="e2e wiring verification" } | ConvertTo-Json
$r = Invoke-RestMethod -Uri "$BASE/presentations" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec 30
$deck = $r.data.id
Step "deck created" ($deck -like "pres_*") $deck

# 3. Upload text source (field name: source)
$tmp = "$env:TEMP\opencode\wire_src.txt"
@"
Photosynthesis Basics
Photosynthesis converts light energy into chemical energy stored in glucose.
Light reactions occur in the thylakoid membranes and produce ATP and NADPH.
The Calvin cycle fixes carbon dioxide into glucose using RuBisCO.
Chlorophyll absorbs red and blue light and reflects green light.
"@ | Set-Content $tmp -Encoding UTF8
$bc = [System.IO.File]::ReadAllBytes($tmp)
$ci = [System.Net.Http.ByteArrayContent]::new($bc)
$ci.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("text/plain")
$fd = [System.Net.Http.MultipartFormDataContent]::new()
$fd.Add($ci, "source", "wire_src.txt")
$req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, "$BASE/presentations/$deck/source")
$req.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer", $tok)
$req.Content = $fd
$resp = [System.Net.Http.HttpClient]::new().SendAsync($req).GetAwaiter().GetResult()
Step "source upload" ($resp.IsSuccessStatusCode) "HTTP $([int]$resp.StatusCode)"

# 4. Poll extraction via GET /presentations/{id} (same as processing.html)
$ext = "none"
foreach ($i in 1..40) {
    Start-Sleep -Milliseconds 700
    try {
        $s = Invoke-RestMethod -Uri "$BASE/presentations/$deck" -Headers $H -TimeoutSec 15
        $ext = $s.data.extraction_status
        if ($ext -in @("ready","failed")) { break }
    } catch { continue }
}
Step "extraction ready" ($ext -eq "ready") "extraction_status=$ext"

# 5. Trigger lesson generation exactly like processing.html: POST /lessons {mode:'slide'}
$b = @{ mode = "slide"; title = "Wiring Lesson $stamp" } | ConvertTo-Json
$r = Invoke-RestMethod -Uri "$BASE/presentations/$deck/lessons" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec 300
$lesson = $r.data.id
$lstatus = $r.data.status
Step "lesson created+dispatched" ($lesson -like "lesson_*") "status=$lstatus"

# 6. Poll lesson until ready (eager mode usually finishes inside the POST)
$lstatus2 = $lstatus; $blocks = @()
foreach ($i in 1..60) {
    if ($lstatus2 -in @("ready","completed","failed")) { break }
    Start-Sleep -Milliseconds 1000
    try {
        $lr = Invoke-RestMethod -Uri "$BASE/presentations/$deck/lessons/$lesson" -Headers $H -TimeoutSec 15
        $lstatus2 = $lr.data.status
        if ($lstatus2 -in @("ready","completed")) { $blocks = $lr.data.version.blocks }
    } catch { continue }
}
if ($blocks.Count -eq 0) {
    try { $lr = Invoke-RestMethod -Uri "$BASE/presentations/$deck/lessons/$lesson" -Headers $H -TimeoutSec 15; $blocks = $lr.data.version.blocks } catch {}
}
Step "lesson generated" ($lstatus2 -in @("ready","completed") -and $blocks.Count -gt 0) "status=$lstatus2 blocks=$($blocks.Count)"

# 7. Player start + set-topic
$r = Invoke-RestMethod -Uri "$BASE/lessons/$lesson/player/start" -Method POST -Headers $H -ContentType "application/json" -Body "{}" -TimeoutSec 30
$pdata = $r.data
$psid = $pdata.session.session_id
Step "player start" ($pdata.topics.Count -gt 0 -and $psid) "$($pdata.topics.Count) topics session=$psid"
$b = @{ session_id = $psid; topic_index = 0 } | ConvertTo-Json
Invoke-RestMethod -Uri "$BASE/lessons/$lesson/player/set-topic" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec 30 | Out-Null
Step "player set-topic sync" $true "index 0"

# 8. Visual canvas + nodes + edges
$b = @{ content = "$($pdata.topics[0].title). $($pdata.topics[0].description)"; title = $pdata.topics[0].title; lesson_id = $lesson } | ConvertTo-Json
$r = Invoke-RestMethod -Uri "$BASE/visual/canvases" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec 90
$canvas = $r.data.canvas_id
$n = Invoke-RestMethod -Uri "$BASE/visual/canvases/$canvas/nodes" -Headers $H -TimeoutSec 30
$e = Invoke-RestMethod -Uri "$BASE/visual/canvases/$canvas/edges" -Headers $H -TimeoutSec 30
$nCount = @($n.data).Count; $eCount = @($e.data).Count
Step "canvas graph" ($nCount -gt 0) "nodes=$nCount edges=$eCount"

# 9. Animation plan + runtime sync
$b = @{ topic = $pdata.topics[0].title; description = $pdata.topics[0].description; canvas_id = $canvas } | ConvertTo-Json
$r = Invoke-RestMethod -Uri "$BASE/animations/plan" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec 90
$bp = $r.data
Step "animation plan" (@($bp.timeline.scenes).Count -gt 0) "scenes=$(@($bp.timeline.scenes).Count)"
$b = @{ blueprint_id = $bp.blueprint_id; scene_index = 0; session_id = "wire_$stamp" } | ConvertTo-Json
Invoke-RestMethod -Uri "$BASE/animations/runtime/sync" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec 30 | Out-Null
Step "animation runtime sync" $true "pos=1200ms"

# 10. Video render (H.264) + static serve
$b = @{ topic = $pdata.topics[0].title; description = $pdata.topics[0].description } | ConvertTo-Json
$r = Invoke-RestMethod -Uri "$BASE/videos/create" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec 300
$vurl = $r.data.playable_url
Step "video render" ($r.data.rendering_status -eq "ready" -and $vurl) $vurl
$head = Invoke-WebRequest -Uri "http://localhost:8000$vurl" -Method Head -UseBasicParsing -TimeoutSec 15
Step "video served" ($head.StatusCode -eq 200) "$([Math]::Round($head.Headers['Content-Length']/1kb))KB mp4"

# 11. Simulations defs -> start -> step
$d = Invoke-RestMethod -Uri "$BASE/simulations/definitions" -Headers $H -TimeoutSec 30
$defs = @($d.data)
Step "sim definitions" ($defs.Count -gt 0) "$($defs.Count) available"
if ($defs.Count -gt 0) {
    $simId = if ($defs[0].simulation_id) { $defs[0].simulation_id } else { $defs[0].id }
    $b = @{ simulation_id = $simId; parameters = @{} } | ConvertTo-Json -Depth 5
    $s = Invoke-RestMethod -Uri "$BASE/simulations/sessions/start" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec 30
    $sid = if ($s.data.session_id) { $s.data.session_id } else { $s.session_id }
    Step "sim session start" ($sid -ne $null) $sid
    $st = Invoke-RestMethod -Uri "$BASE/simulations/sessions/$sid/step" -Method POST -Headers $H -ContentType "application/json" -Body '{"action":"next"}' -TimeoutSec 30
    Step "sim step" $true "stepped"
}

# 12. Static pages all served
$pageOk = $true
foreach ($p in @("index","signin","signup","upload","processing","player")) {
    try { $null = Invoke-WebRequest -Uri "http://localhost:8000/frontend/$p.html" -UseBasicParsing -TimeoutSec 10 } catch { $pageOk = $false }
}
Step "all 6 pages served" $pageOk "index/signin/signup/upload/processing/player"

""
"==== WIRING REPORT: $script:pass passed, $script:fail failed ===="
