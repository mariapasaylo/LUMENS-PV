param(
    [int]$StartRank = 1,
    [int]$EndRank = 62
)

$ErrorActionPreference = "Continue"

$Base = "C:\LUMENS"
$PilotUrl = "http://192.168.168.1:8765/scripts/sadc_edit_active_pilot.ps1"
$UploadUrl = "http://192.168.168.1:8766/upload/sadc_gui_batch_bundle.zip"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BatchRoot = Join-Path $Base "sadc_gui_batch_$Stamp"
$OutputRoot = Join-Path $BatchRoot "outputs"
$LogRoot = Join-Path $BatchRoot "logs"
$StatusCsv = Join-Path $BatchRoot "sadc_gui_batch_status.csv"
$BatchLog = Join-Path $BatchRoot "sadc_gui_batch.log"
$PilotScript = Join-Path $Base "sadc_edit_active_pilot.ps1"
New-Item -ItemType Directory -Force -Path $BatchRoot, $OutputRoot, $LogRoot | Out-Null

function Write-Line($Text) { $Text | Tee-Object -FilePath $BatchLog -Append }

function Upload-Batch {
    $Zip = Join-Path $Base "sadc_gui_batch_bundle.zip"
    if (Test-Path $Zip) { Remove-Item -Force $Zip }
    Compress-Archive -Force -Path $BatchRoot -DestinationPath $Zip
    curl.exe -s -S -H "Expect:" -T "$Zip" $UploadUrl | Out-File -FilePath (Join-Path $BatchRoot "last_upload_response.txt")
    Write-Line "uploaded_batch_zip=$Zip size=$((Get-Item $Zip).Length)"
}

function Append-Pilot-Status($PilotDir) {
    $PilotStatus = Join-Path $PilotDir "sadc_edit_active_pilot_status.csv"
    if (-not (Test-Path $PilotStatus)) {
        Add-Content -Path $StatusCsv -Value ("`"NA`",`"NA`",`"NA`",`"failed`",`"`",`"`",`"missing pilot status: $PilotDir`",`"NA`"")
        return
    }
    $Lines = Get-Content $PilotStatus
    if (-not (Test-Path $StatusCsv)) {
        $Lines[0] -replace "^rank,", "rank," | Set-Content -Path $StatusCsv -Encoding UTF8
    }
    if ($Lines.Count -gt 1) {
        Add-Content -Path $StatusCsv -Value $Lines[1] -Encoding UTF8
    }
}

function Copy-Pilot-Artifacts($PilotDir, $Rank) {
    $RankPrefix = "{0:D2}" -f $Rank
    $RankLogDir = Join-Path $LogRoot $RankPrefix
    New-Item -ItemType Directory -Force -Path $RankLogDir | Out-Null
    Copy-Item -Force (Join-Path $PilotDir "sadc_edit_active_pilot.log") (Join-Path $RankLogDir "sadc_edit_active_pilot.log") -ErrorAction SilentlyContinue
    Copy-Item -Force (Join-Path $PilotDir "sadc_edit_active_pilot_status.csv") (Join-Path $RankLogDir "sadc_edit_active_pilot_status.csv") -ErrorAction SilentlyContinue
    Get-ChildItem -Path (Join-Path $PilotDir "outputs") -Filter "*.dat" -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -Force $_.FullName (Join-Path $OutputRoot $_.Name)
    }
    Get-ChildItem -Path $PilotDir -Filter "*not_validated*.png" -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -Force $_.FullName (Join-Path $RankLogDir $_.Name)
    }
    Get-ChildItem -Path $PilotDir -Filter "*timeout*.png" -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -Force $_.FullName (Join-Path $RankLogDir $_.Name)
    }
    Get-ChildItem -Path $PilotDir -Filter "error.png" -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -Force $_.FullName (Join-Path $RankLogDir $_.Name)
    }
}

Write-Line "batch_start=$(Get-Date -Format o) start_rank=$StartRank end_rank=$EndRank"
curl.exe -L -f -s -S -o "$PilotScript" $PilotUrl

for ($Rank = $StartRank; $Rank -le $EndRank; $Rank++) {
    $Before = Get-Date
    Write-Line "rank_start rank=$Rank time=$($Before.ToString('o'))"
    powershell.exe -ExecutionPolicy Bypass -File $PilotScript -Rank $Rank
    $After = Get-Date
    $PilotDir = Get-ChildItem -Path $Base -Directory -Filter "sadc_edit_active_pilot_*" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $PilotDir) {
        Add-Content -Path $StatusCsv -Value ("`"$Rank`",`"`",`"`",`"failed`",`"`",`"`",`"pilot directory not found`",`"$([int]($After-$Before).TotalSeconds)`"")
        Write-Line "rank_done rank=$Rank status=failed reason=pilot_directory_not_found seconds=$([int]($After-$Before).TotalSeconds)"
    } else {
        Append-Pilot-Status $PilotDir.FullName
        Copy-Pilot-Artifacts $PilotDir.FullName $Rank
        $LastStatus = Import-Csv (Join-Path $PilotDir.FullName "sadc_edit_active_pilot_status.csv") | Select-Object -First 1
        Write-Line "rank_done rank=$Rank status=$($LastStatus.status) formula=$($LastStatus.formula) seconds=$([int]($After-$Before).TotalSeconds) pilot_dir=$($PilotDir.FullName)"
    }
    Upload-Batch
}

Write-Line "batch_done=$(Get-Date -Format o)"
Upload-Batch
