# Push US Product Search app to https://github.com/jiaxianh/sku_check
# Run from project root:  .\push_sku_check.ps1

$ErrorActionPreference = "Stop"
$Remote = "https://github.com/jiaxianh/sku_check.git"

function Find-Git {
    $candidates = @(
        "git",
        "${env:ProgramFiles}\Git\bin\git.exe",
        "${env:ProgramFiles}\Git\cmd\git.exe",
        "${env:ProgramFiles(x86)}\Git\bin\git.exe"
    )
    foreach ($p in $candidates) {
        if ($p -eq "git") {
            try {
                $null = Get-Command git -ErrorAction Stop
                return "git"
            } catch { }
        } elseif (Test-Path $p) { return $p }
    }
    return $null
}

$git = Find-Git
if (-not $git) {
    Write-Host "Git not found. Install Git for Windows and reopen the terminal:"
    Write-Host "  https://git-scm.com/download/win"
    exit 1
}

Write-Host "Using: $git"
& $git --version

if (-not (Test-Path "app.py")) {
    Write-Host "Run this script from the folder that contains app.py (AI test)."
    exit 1
}

function Test-GitIdentity {
    $email = (& $git config user.email 2>$null).Trim()
    $name = (& $git config user.name 2>$null).Trim()
    if (-not $email) { $email = (& $git config --global user.email 2>$null).Trim() }
    if (-not $name) { $name = (& $git config --global user.name 2>$null).Trim() }
    return [pscustomobject]@{ Email = $email; Name = $name }
}

& $git init
& $git branch -M main

$id = Test-GitIdentity
if (-not $id.Email -or -not $id.Name) {
    Write-Host ""
    Write-Host "Git needs your name and email before the first commit. Run (use your real info):"
    Write-Host '  git config --global user.email "you@example.com"'
    Write-Host '  git config --global user.name "Your Name"'
    Write-Host ""
    Write-Host "Or set only for this repo (omit --global):"
    Write-Host '  git config user.email "you@example.com"'
    Write-Host '  git config user.name "Your Name"'
    Write-Host ""
    Write-Host "Then run this script again:  .\push_sku_check.ps1"
    exit 1
}

$files = @(
    "app.py",
    "src",
    "requirements.txt",
    "runtime.txt",
    ".gitignore",
    "README.md",
    "DEPLOY_STREAMLIT_CLOUD.zh.md",
    "GITHUB_PUSH_SKU_CHECK.md",
    "push_sku_check.ps1",
    ".streamlit/config.toml",
    "run.bat"
)
foreach ($f in $files) {
    if (Test-Path $f) { & $git add -- $f }
}

& $git status

$staged = & $git diff --cached --name-only
if (-not $staged) {
    Write-Host "Nothing staged. Check that app.py and src/ exist."
    exit 1
}

& $git commit -m "Initial: US product search Streamlit app"
$commitExit = $LASTEXITCODE

$null = & $git rev-parse HEAD 2>&1
$haveHead = ($LASTEXITCODE -eq 0)

if (-not $haveHead) {
    Write-Host ""
    Write-Host "No commit was created. Fix the error above (usually: set user.name / user.email), then run again."
    Write-Host "After fixing:  git log -1 --oneline  should show your commit."
    exit 1
}

if ($commitExit -ne 0) {
    Write-Host "Nothing new to commit (tree already committed). Continuing to push..."
}

$remotes = & $git remote 2>$null
if ($remotes -contains "origin") {
    & $git remote set-url origin $Remote
} else {
    & $git remote add origin $Remote
}

Write-Host ""
Write-Host "Pushing to origin main..."
& $git push -u origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "Push failed. If the repo is empty, ensure commit succeeded first."
    exit 1
}
Write-Host "Done. Repo: $Remote"
