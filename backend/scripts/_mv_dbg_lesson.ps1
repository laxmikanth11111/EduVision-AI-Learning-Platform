$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http
$BASE = "http://localhost:8000/api/v1"
$EXTRACT_TIMEOUT_SEC = 180
$LESSON_TIMEOUT_SEC  = 300
$stamp = Get-Random -Maximum 99999
$email = "dbg$stamp@t.com"

function Poll-Until([scriptblock]$Check, [int]$TimeoutSec, [string]$Label, [scriptblock]$Status) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $val = $null
    $errorCount = 0
    $pollCount = 0
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        try {
            $val = & $Status
        } catch {
            $val = "query-error"
            $errorCount++
            Write-Host ("polling {0} ... query-error at {1}s: {2}" -f $Label, [int]$sw.Elapsed.TotalSeconds, $_.Exception.Message)
            Start-Sleep -Seconds 2
            continue
        }
        $pollCount++
        Write-Host "polling $Label ... status=$val elapsed=$([int]$sw.Elapsed.TotalSeconds)s"
        if (& $Check $val) { return $val }
        Start-Sleep -Seconds 2
    }
    if ($pollCount -eq 0) {
        Write-Host "ERROR: API became unreachable during ${Label} polling (timeout after ${TimeoutSec} seconds, ${errorCount} polls all failed)"
    } else {
        Write-Host "ERROR: ${Label} polling timeout after ${TimeoutSec} seconds (last status=$val)"
    }
    exit 1
}

# 1. Register + login
$b = @{ email=$email; password="DbgTest123!"; name="D" } | ConvertTo-Json
$r = Invoke-RestMethod -Uri "$BASE/auth/register" -Method POST -ContentType "application/json" -Body $b -TimeoutSec 30
$tok = $r.tokens.access_token
$H = @{ Authorization = "Bearer $tok" }
Write-Host "auth ok"

# 2. Deck
$b = @{ title="Dbg $stamp" } | ConvertTo-Json
$deck = (Invoke-RestMethod -Uri "$BASE/presentations" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec 30).data.id
Write-Host "deck: $deck"

# 3. Upload text source
$tmp = "$env:TEMP\opencode\dbg_src.txt"
@"
Newton's Laws of Motion
The first law states objects remain at rest or in uniform motion unless acted upon by an external force.
The second law relates force, mass and acceleration through F equals m times a.
The third law states every action has an equal and opposite reaction.
"@ | Set-Content $tmp -Encoding UTF8
$bc = [System.IO.File]::ReadAllBytes($tmp)
$ci = [System.Net.Http.ByteArrayContent]::new($bc)
$ci.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("text/plain")
$fd = [System.Net.Http.MultipartFormDataContent]::new()
$fd.Add($ci, "source", "dbg_src.txt")
$req = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Post, "$BASE/presentations/$deck/source")
$req.Headers.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer", $tok)
$req.Content = $fd
$resp = [System.Net.Http.HttpClient]::new().SendAsync($req).GetAwaiter().GetResult()
if (-not $resp.IsSuccessStatusCode) { Write-Host "ERROR: upload failed HTTP $([int]$resp.StatusCode)"; exit 1 }
Write-Host "upload: 200"

# 4. Bounded extraction polling
$ext = Poll-Until -Label "extraction" -TimeoutSec $EXTRACT_TIMEOUT_SEC `
    -Status { (Invoke-RestMethod -Uri "$BASE/presentations/$deck" -Headers $H -TimeoutSec 15).data.extraction_status } `
    -Check { param($v) $v -eq "ready" }
if ($ext -ne "ready") { Write-Host "ERROR: extraction ended as $ext"; exit 1 }

# 5. Create lesson (triggers eager generation)
$b = @{ mode = "slide"; title = "Dbg Lesson $stamp" } | ConvertTo-Json
$lr = Invoke-RestMethod -Uri "$BASE/presentations/$deck/lessons" -Method POST -Headers $H -ContentType "application/json" -Body $b -TimeoutSec 300
$lesson = $lr.data.id
Write-Host "lesson: $lesson initial status: $($lr.data.status)"

# 6. Bounded lesson polling
$final = Poll-Until -Label "lesson-generation" -TimeoutSec $LESSON_TIMEOUT_SEC `
    -Status { (Invoke-RestMethod -Uri "$BASE/presentations/$deck/lessons/$lesson" -Headers $H -TimeoutSec 15).data.status } `
    -Check { param($v) $v -in @("ready","completed","failed") }

$d = (Invoke-RestMethod -Uri "$BASE/presentations/$deck/lessons/$lesson" -Headers $H -TimeoutSec 15).data
Write-Host ""
Write-Host "==== RESULT ===="
Write-Host "presentation : $deck"
Write-Host "lesson       : $lesson"
Write-Host "status       : $($d.status)"
$blockCount = 0
if ($d.version -and $d.version.blocks) { $blockCount = @($d.version.blocks).Count }
Write-Host "blocks       : $blockCount"
if ($d.retry_state)   { Write-Host "retry_state  : $($d.status) / $($d.retry_state)" }
if ($d.error_message) { Write-Host "error        : $($d.error_message)" }
if ($final -eq "failed") {
    Write-Host ""
    Write-Host "full lesson detail:"
    $d | ConvertTo-Json -Depth 6
    exit 1
}
Write-Host "OK"
