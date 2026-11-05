# MusicMake setup for Windows (PowerShell).
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#   ... -NoStudio     skip building SoundCraft (needs Rust, ~10 minutes)
#   ... -NoAceStep    skip ACE-Step 1.5 (the GPU song engine)
#   ... -NoStems      skip Demucs (stems for any song)
# Set $env:TORCH_INDEX to pick a PyTorch build, e.g. https://download.pytorch.org/whl/cu128
param(
    [switch]$NoAceStep,
    [switch]$NoStudio,
    [switch]$NoStems
)
$ErrorActionPreference = "Stop"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Run($exe, [string[]]$arguments) {
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "Failed: $exe $($arguments -join ' ')" }
}

Set-Location (Join-Path $PSScriptRoot "..")
$Root = (Get-Location).Path

# Python 3.11+ (the py launcher comes with python.org installers)
$Py = $null
if (Have "py") { $Py = "py"; $PyArgs = @("-3") } elseif (Have "python") { $Py = "python"; $PyArgs = @() }
if (-not $Py) { throw "Install Python 3.11 or newer from https://www.python.org/downloads/ (tick 'Add to PATH')." }
& $Py @PyArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) { throw "MusicMake needs Python 3.11 or newer." }

Step "Python environment (.venv)"
if (-not (Test-Path ".venv")) { Run $Py ($PyArgs + @("-m", "venv", ".venv")) }
$VPy = Join-Path $Root ".venv\Scripts\python.exe"
Run $VPy @("-m", "pip", "install", "--upgrade", "pip", "-q")
Run $VPy @("-m", "pip", "install", "-r", "requirements.txt", "pytest", "-q")

if (-not $NoStems) {
    Step "Demucs for stems"
    if (Have "nvidia-smi") {
        $index = if ($env:TORCH_INDEX) { $env:TORCH_INDEX } else { "https://download.pytorch.org/whl/cu128" }
        Run $VPy @("-m", "pip", "install", "torch", "torchaudio", "--index-url", $index, "-q")
    }
    Run $VPy @("-m", "pip", "install", "demucs", "-q")
}

if (-not $NoAceStep) {
    Step "ACE-Step 1.5 (in ..\ACE-Step-1.5)"
    if (-not (Have "uv")) {
        Write-Host "Installing uv (ACE-Step's package manager)..."
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    }
    $Ace = Join-Path (Split-Path $Root -Parent) "ACE-Step-1.5"
    if (-not (Test-Path $Ace)) { Run "git" @("clone", "https://github.com/ACE-Step/ACE-Step-1.5.git", $Ace) }
    Push-Location $Ace
    try { Run "uv" @("sync") } finally { Pop-Location }
    Write-Host "Models download the first time the server starts (several GB)."
}

if (-not $NoStudio) {
    Step "SoundCraft command-line tool (Studio)"
    if (Have "soundcraft-cli") {
        Write-Host "Already installed: $(soundcraft-cli --version)"
    } elseif (Have "cargo") {
        Run "cargo" @("install", "--locked", "--git", "https://github.com/storytold/soundcraft", "soundcraft-cli")
    } else {
        Write-Host "Rust isn't installed, so Studio is skipped for now."
        Write-Host "Install Rust from https://rustup.rs (it also asks for the Visual Studio C++ Build Tools), then run:"
        Write-Host "  cargo install --locked --git https://github.com/storytold/soundcraft soundcraft-cli"
    }
}

if (-not (Have "ffmpeg")) { Write-Host "Tip: install ffmpeg for MP3 export and uploads:  winget install Gyan.FFmpeg" }

Step "Check"
& $VPy -m musicmake doctor

Write-Host @"

Next:
  1. Start ACE-Step:   cd ..\ACE-Step-1.5 ; uv run acestep-api
  2. Start MusicMake:  .venv\Scripts\python.exe -m musicmake
  3. Open http://127.0.0.1:8765
In VS Code: Terminal > Run Task... > "Start everything".
"@
