$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http

$PPTX = "C:\Users\Admin\OneDrive\Desktop\AI visual learning\backend\storage-data\eduvision-content\sources\pres_0d6f47a76274476e\6ad6357e88ce42c5a625bffe469131f5_ML_UNIT3_PPT.pptx"
$EXPECTED_SLIDES = 82
$BASE = "http://localhost:8000/api/v1"
$EXTRACT_TIMEOUT_SEC = 300
$LESSON_TIMEOUT_SEC  = 720

$script:rec = @{}
$script:rec["presentation_id"]        = ""
$script:rec["lesson_id"]              = ""
$script:rec["extraction_status"]      = ""
$script:rec["slide_count"]            = -1
$script:rec["lesson_status"]          = ""
$script:rec["extraction_seconds"]     = -1
$script:rec["generation_seconds"]     = -1
$script:rec["block_count"]            = -1
$script:rec["topic_count"]            = -1
$script:rec["expected_player_slides"] = -1
$script:rec["player_session"]         = ""
$script:rec["error_message"]          = ""
$script:rec["retry_state"]            = ""

function Fail([string]$Msg) {
    Write-Host ""
    Write-Host "==== FAILURE ===="
    Write-Host $Msg
    if ($script:rec["error_message"]) { Write-Host "error_message : $($script:rec['error_message'])" }
    if ($script:rec["retry_state"])   { Write-Host "retry_state   : $($script:rec['retry_state'])" }
    Write-Host ($script:rec | ConvertTo-Json)
    exit 1
}

function Poll-Until([string]$Label, [int]$TimeoutSec, [scriptblock]$Status, [scriptblock]$Check) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $val = $null
    $errCount = 0
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        try { $val = & $Status }
        catch {
            $errCount++
            Write-Host ("polling {0} ... query-error at {1}s: {2}" -f $Label, [int]$sw.Elapsed.TotalSeconds, $_.Exception.Message)
            Start-Sleep -Seconds 2
            continue
        }
        Write-Host "polling $Label ... status=$val elapsed=$([int]$sw.Elapsed.TotalSeconds)s"
        if (& $Check $val) { return ,@($val, [int]$sw.Elapsed.TotalSeconds) }
        Start-Sleep -Seconds 2
    }
    $tail = if ($errCount -gt 0) { " ($errCount query errors)" } else { "" }
    Fail "${Label} polling timed out after ${TimeoutSec}s${tail}; last status=$val"
}

# 0. PPTX must exist
if (-not (Test-Path -LiteralPath $PPTX)) { Fail "PPTX not found: $PPTX" }
$pptBytes = [System.IO.File]::ReadAllBytes($PPTX)
Write-Host ("pptx: {0} ({1} KB)" -f (Split-Path $PPTX -Leaf), [int]($pptBytes.Length/1kb))

# 1. Register fresh test user
$stamp = Get-Random -Maximum 999999
$email = "mlu$stamp@t.com"
try {
    $b = @{ email=$email; password="MluTest123!"; name="MLU" } | ConvertTo-Json
    $r = Invoke-RestMethod -Uri "$BASE/auth/register" -Method POST -ContentType "application/json" -Body $b -TimeoutSec 30
    $tok = $r.tokens.access_token
} catch { Fail "register failed: $($_.Exception.Message)" }
$H = @{ Authorization = "Bearer $tok" }
Write-Host "auth ok: $email"

# 2. Create fresh presentation
try {
    $b = @{ title = "ML_UNIT3 real-world test $stamp" } | ConvertTo-Json
    $deck = (Invoke-RestMethod -Uri "$BASE/presentations" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec 30).data.id
} catch { Fail "deck creation failed: $($_.Exception.Message)" }
$script:rec["presentation_id"] = $deck
Write-Host "deck: $deck"

# 3. Upload PPTX (normal app flow: POST /presentations/{id}/source, field 'source')
$ci = [System.Net.Http.ByteArrayContent]::new($pptBytes)
$ci.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("application/vnd.openxmlformats-officedocument.presentationml.presentation")
$fd = [System.Net.Http.MultipartFormDataContent]::new()
$fd.Add($ci, "source", "ML_UNIT3_PPT.pptx")
$req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, "$BASE/presentations/$deck/source")
$req.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer", $tok)
$req.Content = $fd
$hc = [System.Net.Http.HttpClient]::new()
$hc.Timeout = [TimeSpan]::FromSeconds(120)
try { $resp = $hc.SendAsync($req).GetAwaiter().GetResult() } catch { Fail "upload threw: $($_.Exception.Message)" }
if (-not $resp.IsSuccessStatusCode) {
    $body = ""
    try { $body = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult() } catch {}
    Fail ("upload failed HTTP {0}: {1}" -f [int]$resp.StatusCode, $body.Substring(0, [Math]::Min(500, $body.Length)))
}
Write-Host "upload: HTTP $([int]$resp.StatusCode)"

# 4. Bounded extraction polling (<= 300s), require ready
$out = Poll-Until -Label "extraction" -TimeoutSec $EXTRACT_TIMEOUT_SEC `
    -Status { (Invoke-RestMethod -Uri "$BASE/presentations/$deck" -Headers $H -TimeoutSec 15).data.extraction_status } `
    -Check { param($v) $v -eq "ready" }
$script:rec["extraction_status"]  = $out[0]
$script:rec["extraction_seconds"] = $out[1]
Write-Host ("extraction ready in {0}s" -f $out[1])

# 5. Confirm extracted slide count = 82
$d = (Invoke-RestMethod -Uri "$BASE/presentations/$deck" -Headers $H -TimeoutSec 15).data
$script:rec["slide_count"] = $d.slide_count
if ($d.slide_count -ne $EXPECTED_SLIDES) {
    Fail "slide_count mismatch: got $($d.slide_count), expected $EXPECTED_SLIDES"
}
Write-Host "slide_count: $($d.slide_count) (matches source)"

# 6. Trigger lesson generation exactly like processing.html: POST /lessons {mode:'slide'}
$b = @{ mode = "slide" } | ConvertTo-Json
$genSw = [Diagnostics.Stopwatch]::StartNew()
try {
    $lr = Invoke-RestMethod -Uri "$BASE/presentations/$deck/lessons" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec ($LESSON_TIMEOUT_SEC + 30)
} catch {
    Fail "lesson POST threw after $([int]$genSw.Elapsed.TotalSeconds)s: $($_.Exception.Message)"
}
$lesson = $lr.data.id
$script:rec["lesson_id"] = $lesson
Write-Host "lesson: $lesson initial status: $($lr.data.status)"
if (-not $lesson) { Fail "lesson POST returned no id" }

# 7. Bounded lesson polling (<= 720s) until ready/completed/failed
$out = Poll-Until -Label "lesson-generation" -TimeoutSec $LESSON_TIMEOUT_SEC `
    -Status { (Invoke-RestMethod -Uri "$BASE/presentations/$deck/lessons/$lesson" -Headers $H -TimeoutSec 15).data.status } `
    -Check { param($v) $v -in @("ready","completed","failed") }
$script:rec["lesson_status"]        = $out[0]
$script:rec["generation_seconds"]   = $out[1]

# 8. Full lesson detail
$d = (Invoke-RestMethod -Uri "$BASE/presentations/$deck/lessons/$lesson" -Headers $H -TimeoutSec 15).data
$blockCount = 0
if ($d.version -and $d.version.blocks) { $blockCount = @($d.version.blocks).Count }
$script:rec["block_count"] = $blockCount
if ($d.error_message) { $script:rec["error_message"] = $d.error_message }
if ($d.retry_state)   { $script:rec["retry_state"] = $d.retry_state }

if ($d.status -eq "failed") {
    Write-Host ""
    Write-Host "==== LESSON FAILED - FULL DIAGNOSTIC DUMP ===="
    $d | ConvertTo-Json -Depth 6
    Fail "lesson status=failed blocks_before_failure=$blockCount elapsed=$($script:rec['generation_seconds'])s"
}
if ($d.status -notin @("ready","completed")) {
    Fail "unexpected final lesson status: $($d.status)"
}
if ($blockCount -le 0) {
    Fail "lesson $($d.status) but block_count=0"
}
Write-Host ("lesson {0}: {1} blocks in {2}s" -f $d.status, $blockCount, $script:rec["generation_seconds"])

# 9. Player start (lazy visuals: no bulk visual generation here)
$topicCount = 0
try {
    $pr = Invoke-RestMethod -Uri "$BASE/lessons/$lesson/player/start" -Method POST -Headers $H -ContentType "application/json" -Body "{}" -TimeoutSec 60
    $pdata = $pr.data
    $script:rec["player_session"] = $pdata.session.session_id
    $topicCount = @($pdata.topics).Count
    if (-not $topicCount -and $pdata.total_topics) { $topicCount = $pdata.total_topics }
} catch { Fail "player/start failed: $($_.Exception.Message)" }
$script:rec["topic_count"] = $topicCount
$script:rec["expected_player_slides"] = $topicCount * 2

if (-not $script:rec["player_session"]) { Fail "player/start returned no session_id" }
if ($topicCount -le 0)                { Fail "player/start returned 0 topics" }
Write-Host "player start ok: session=$($script:rec['player_session']) topics=$topicCount"

# 10. Structured RESULT
Write-Host ""
Write-Host "================ RESULT ================"
foreach ($k in $script:rec.Keys) { Write-Host ("{0,-22}: {1}" -f $k, $script:rec[$k]) }
Write-Host "========================================="
Write-Host "PASS"
exit 0
