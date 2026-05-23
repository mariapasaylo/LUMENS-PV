param(
    [int]$Rank = 1
)

$ErrorActionPreference = "Continue"

$Base = "C:\LUMENS"
$OmereRoot = Join-Path $Base "omere_min\OMERE581"
$OmereExe = Join-Path $OmereRoot "Omere.exe"
$BundleUrl = "http://192.168.168.1:8765/sadc_input_bundles_20260523.zip"
$UploadUrl = "http://192.168.168.1:8766/upload/sadc_edit_active_pilot_bundle.zip"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$RunRoot = Join-Path $Base "sadc_edit_active_pilot_$Stamp"
$InputZip = Join-Path $RunRoot "sadc_input_bundles_20260523.zip"
$InputRoot = Join-Path $RunRoot "inputs"
$OutputRoot = Join-Path $RunRoot "outputs"
$LogRoot = Join-Path $RunRoot "logs"
New-Item -ItemType Directory -Force -Path $RunRoot, $InputRoot, $OutputRoot, $LogRoot | Out-Null
$Log = Join-Path $RunRoot "sadc_edit_active_pilot.log"
$StatusCsv = Join-Path $RunRoot "sadc_edit_active_pilot_status.csv"

function Write-Line($Text) { $Text | Tee-Object -FilePath $Log -Append }
function Csv-Quote($Value) { return '"' + ([string]$Value).Replace('"', '""') + '"' }
function Add-Status($Rank, $Formula, $MaterialId, $Status, $OutputFile, $Bytes, $ErrorText, $Seconds) {
    $Fields = @($Rank, $Formula, $MaterialId, $Status, $OutputFile, $Bytes, $ErrorText, $Seconds) | ForEach-Object { Csv-Quote $_ }
    Add-Content -Path $StatusCsv -Value ($Fields -join ",") -Encoding UTF8
}
Add-Content -Path $StatusCsv -Value "rank,formula,material_id,status,output_file,bytes,error,seconds" -Encoding UTF8

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class NativeSadcEdit {
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);
}
"@

function Click-At($X, $Y) {
    [NativeSadcEdit]::SetCursorPos($X, $Y) | Out-Null
    Start-Sleep -Milliseconds 80
    [NativeSadcEdit]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [NativeSadcEdit]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 250
}

function Save-Screenshot($Name) {
    $Bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $Bmp = New-Object System.Drawing.Bitmap $Bounds.Width, $Bounds.Height
    $Graphics = [System.Drawing.Graphics]::FromImage($Bmp)
    $Graphics.CopyFromScreen($Bounds.Location, [System.Drawing.Point]::Empty, $Bounds.Size)
    $Path = Join-Path $RunRoot $Name
    $Bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $Graphics.Dispose()
    $Bmp.Dispose()
}

function Send-Text($Text) {
    try {
        [System.Windows.Forms.Clipboard]::SetText([string]$Text)
        Start-Sleep -Milliseconds 100
        [System.Windows.Forms.SendKeys]::SendWait("^v")
    } catch {
        [System.Windows.Forms.SendKeys]::SendWait([string]$Text)
    }
    Start-Sleep -Milliseconds 200
}

function Set-FieldAt($X, $Y, $Text) {
    Click-At $X $Y
    Start-Sleep -Milliseconds 100
    [System.Windows.Forms.SendKeys]::SendWait("^a")
    Start-Sleep -Milliseconds 100
    Send-Text $Text
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Start-Sleep -Milliseconds 300
}

function Select-CustomComboAt($X, $Y) {
    Click-At $X $Y
    Start-Sleep -Milliseconds 300
    # Qt's property-tree combo does not reliably open from Alt+Down under Wine.
    # The dropdown is anchored under the value cell; Custom is the fifth item.
    Click-At ([int]($X - 575)) ([int]($Y + 200))
    Start-Sleep -Milliseconds 600
}

function Find-First($Root, $TypeName, $Name) {
    $type = [System.Windows.Automation.ControlType]::$TypeName
    $c1 = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, $type)
    $c2 = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, $Name)
    $cond = New-Object System.Windows.Automation.AndCondition($c1, $c2)
    return $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
}

function Find-DegradationCombo($Dialog) {
    $NameCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Degradation Model")
    $Items = $Dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants, $NameCondition)
    foreach ($Item in $Items) {
        $Rect = $Item.Current.BoundingRectangle
        if ($Item.Current.ClassName -eq "QWidget" -and $Rect.Height -lt 40 -and $Rect.Width -gt 100) {
            return $Item
        }
    }
    return $null
}

function Wait-For-Output($Path, $TimeoutSeconds) {
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $LastLength = -1
    $StableCount = 0
    while ((Get-Date) -lt $Deadline) {
        if (Test-Path $Path) {
            $Length = (Get-Item $Path).Length
            if ($Length -gt 0 -and $Length -eq $LastLength) {
                $StableCount += 1
            } else {
                $StableCount = 0
                $LastLength = $Length
            }
            if ($StableCount -ge 3) { return $true }
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Stop-Omere {
    Get-Process -Name "Omere" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

function Upload-Run {
    $Zip = Join-Path $Base "sadc_edit_active_pilot_bundle.zip"
    if (Test-Path $Zip) { Remove-Item -Force $Zip }
    Compress-Archive -Force -Path $RunRoot -DestinationPath $Zip
    curl.exe -s -S -H "Expect:" -T "$Zip" $UploadUrl | Out-File -FilePath (Join-Path $RunRoot "upload_response.txt")
    Write-Line "uploaded=$Zip size=$((Get-Item $Zip).Length)"
}

$StartTime = Get-Date
try {
    Write-Line "start=$(Get-Date -Format o)"
    curl.exe -L -f -s -S -o "$InputZip" $BundleUrl
    Expand-Archive -Force -LiteralPath $InputZip -DestinationPath $InputRoot
    $BundleRoot = Join-Path $InputRoot "sadc_input_bundles"
    $Manifest = Join-Path $BundleRoot "sadc_run_manifest.csv"
    $Row = Import-Csv $Manifest | Where-Object {[int]$_.srniel_damage_rank -eq $Rank} | Select-Object -First 1
    if ($null -eq $Row) { throw "rank $Rank not found in manifest" }
    $BundleDir = Join-Path $InputRoot (Split-Path $Row.cell_json -Parent)
    $Cell = Get-Content -Raw (Join-Path $BundleDir "Cell.json") | ConvertFrom-Json
    $Active = $Cell.layers | Where-Object {$_.type -eq "active"} | Select-Object -First 1
    $Formula = [string]$Row.formula
    $MaterialId = [string]$Row.material_id
    $Density = [string]$Active.density

    $NielRoot = Join-Path $RunRoot "candidate_niel"
    New-Item -ItemType Directory -Force -Path $NielRoot | Out-Null
    $ElectronNiel = Join-Path $NielRoot ("NIEL_e_{0}_{1}.dat" -f $Formula, $MaterialId)
    $ProtonNiel = Join-Path $NielRoot ("NIEL_p_{0}_{1}.dat" -f $Formula, $MaterialId)
    Copy-Item -Force (Join-Path $BundleDir "niel\electron_NIEL.dat") $ElectronNiel
    Copy-Item -Force (Join-Path $BundleDir "niel\proton_NIEL.dat") $ProtonNiel

    $OutName = ("{0:D2}_{1}_{2}.dat" -f [int]$Rank, $Formula, $MaterialId) -replace "[^A-Za-z0-9_.-]+", "_"
    $OutPath = Join-Path $OutputRoot $OutName
    if (Test-Path $OutPath) { Remove-Item -Force $OutPath }
    Write-Line "rank=$Rank formula=$Formula material_id=$MaterialId density=$Density"
    Write-Line "electron_niel=$ElectronNiel"
    Write-Line "proton_niel=$ProtonNiel"
    Write-Line "out=$OutPath"

    Stop-Omere
    $Proc = Start-Process -FilePath $OmereExe -WorkingDirectory $OmereRoot -PassThru
    Start-Sleep -Seconds 6
    $Proc.Refresh()
    $Hwnd = $Proc.MainWindowHandle
    Write-Line "pid=$($Proc.Id) hwnd=$Hwnd"
    [NativeSadcEdit]::SetForegroundWindow($Hwnd) | Out-Null

    $Root = [System.Windows.Automation.AutomationElement]::RootElement
    $PidCondition = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $Proc.Id)
    $Main = $null
    $Dialog = $null
    for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
        $Root = [System.Windows.Automation.AutomationElement]::RootElement
        $Main = $Root.FindFirst([System.Windows.Automation.TreeScope]::Children, $PidCondition)
        if ($null -ne $Main) {
            [NativeSadcEdit]::SetForegroundWindow($Hwnd) | Out-Null
            [NativeSadcEdit]::PostMessage($Hwnd, 0x0111, [IntPtr]36057, [IntPtr]::Zero) | Out-Null
            Start-Sleep -Milliseconds 700
            $Dialog = $Main.FindFirst([System.Windows.Automation.TreeScope]::Descendants, (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Solar Cell Degradation")))
            if ($null -ne $Dialog) { break }
        }
        Start-Sleep -Seconds 1
    }
    if ($null -eq $Dialog) { throw "Solar Cell Degradation dialog not found" }

    $DialogHwnd = [IntPtr]$Dialog.Current.NativeWindowHandle
    [NativeSadcEdit]::SetWindowPos($DialogHwnd, [IntPtr]::Zero, 960, 50, 1250, 1900, 0x0040) | Out-Null
    Start-Sleep -Seconds 1

    $Combo = Find-DegradationCombo $Dialog
    if ($null -eq $Combo) { throw "Degradation Model combo not found" }
    $ComboRect = $Combo.Current.BoundingRectangle
    Click-At ([int]($ComboRect.X + 75)) ([int]($ComboRect.Y + ($ComboRect.Height / 2)))
    [System.Windows.Forms.SendKeys]::SendWait("%{DOWN}")
    Start-Sleep -Milliseconds 700
    $SadcItem = Find-First $Root "ListItem" "SADC"
    if ($null -eq $SadcItem) { throw "SADC list item not found" }
    $SadcRect = $SadcItem.Current.BoundingRectangle
    Click-At ([int]($SadcRect.X + ($SadcRect.Width / 2))) ([int]($SadcRect.Y + ($SadcRect.Height / 2)))
    Start-Sleep -Seconds 2

    $Tree = $Dialog.FindFirst([System.Windows.Automation.TreeScope]::Descendants, (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Tree)))
    if ($null -eq $Tree) { throw "SADC property tree not found" }
    $TreeRect = $Tree.Current.BoundingRectangle
    Write-Line "tree_rect=$TreeRect"
    Click-At ([int]($TreeRect.X + 24)) ([int]($TreeRect.Y + 214))
    Start-Sleep -Milliseconds 700
    Save-Screenshot "01_before_edit.png"

    $ValueX = [int]($TreeRect.X + 540)
    $ComboX = [int]($TreeRect.X + 1138)
    Set-FieldAt $ValueX ([int]($TreeRect.Y + 340)) $Formula
    Set-FieldAt ([int]($TreeRect.X + 915)) ([int]($TreeRect.Y + 460)) $Density
    Set-FieldAt $ValueX ([int]($TreeRect.Y + 500)) $Formula
    Select-CustomComboAt $ComboX ([int]($TreeRect.Y + 620))
    Set-FieldAt $ValueX ([int]($TreeRect.Y + 660)) $ElectronNiel
    Select-CustomComboAt $ComboX ([int]($TreeRect.Y + 700))
    Set-FieldAt $ValueX ([int]($TreeRect.Y + 740)) $ProtonNiel
    Save-Screenshot "02_after_edit.png"

    $OutEdit = Find-First $Dialog "Edit" "Output"
    if ($null -eq $OutEdit) { throw "Output edit not found" }
    try {
        $OutEdit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($OutPath)
    } catch {
        $OutEdit.SetFocus()
        Start-Sleep -Milliseconds 200
        [System.Windows.Forms.SendKeys]::SendWait("^a")
        Send-Text $OutPath
    }
    Save-Screenshot "03_before_calculation.png"

    $CalcButtons = $Dialog.FindAll([System.Windows.Automation.TreeScope]::Descendants, (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty, "Calculation")))
    $Invoked = $false
    foreach ($Button in $CalcButtons) {
        if ($Button.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button -and $Button.Current.IsEnabled) {
            $Button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
            $Invoked = $true
            break
        }
    }
    if (-not $Invoked) { throw "Enabled Calculation button not found" }

    $Complete = Wait-For-Output $OutPath 240
    $Seconds = [int]((Get-Date) - $StartTime).TotalSeconds
    if (-not $Complete) {
        Save-Screenshot "04_timeout.png"
        Add-Status $Rank $Formula $MaterialId "timeout_no_stable_output" $OutPath "" "no stable output within timeout" $Seconds
        Upload-Run
        return
    }

    $OutputText = Get-Content -Raw $OutPath
    $FormulaRegex = [regex]::Escape($Formula)
    $Expected = (
        $OutputText -match ('"{0}"' -f $FormulaRegex) -and
        $OutputText -match ("Composition\s+:\s+{0}" -f $FormulaRegex) -and
        $OutputText -match [regex]::Escape($ElectronNiel) -and
        $OutputText -match [regex]::Escape($ProtonNiel)
    )
    $Bytes = (Get-Item $OutPath).Length
    if ($Expected) {
        Add-Status $Rank $Formula $MaterialId "completed_validated" $OutPath $Bytes "" $Seconds
    } else {
        Add-Status $Rank $Formula $MaterialId "completed_not_validated" $OutPath $Bytes "output did not contain expected candidate formula and explicit candidate NIEL paths" $Seconds
        Save-Screenshot "04_not_validated.png"
    }
    Write-Line "expected=$Expected bytes=$Bytes seconds=$Seconds"
    Upload-Run
} catch {
    $Seconds = [int]((Get-Date) - $StartTime).TotalSeconds
    $Err = $_.Exception.Message
    try { Save-Screenshot "error.png" } catch {}
    Add-Status $Rank "" "" "failed" "" "" $Err $Seconds
    Write-Line "failed=$Err seconds=$Seconds"
    Upload-Run
} finally {
    Stop-Omere
}
