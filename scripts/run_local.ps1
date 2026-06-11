<#
Sobe o assistente LOCALMENTE com um comando, SEM Docker: API (uvicorn) + UI (Streamlit),
usando a .venv do próprio projeto. Cada serviço abre numa janela minimizada (logs visíveis
e fáceis de fechar); o navegador abre sozinho na UI quando tudo está de pé.

Por que existe além do docker-compose: nem toda máquina (ex.: este Windows) tem Docker —
este script é o caminho "1 comando" equivalente para quem só tem o Python/venv do repo.

Uso (na raiz do projeto ou de qualquer lugar):
  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1              # sobe tudo
  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 -Stop        # derruba
  powershell ... run_local.ps1 -ApiPort 8010 -UiPort 8511                     # portas alternativas
#>
param(
    [int]$ApiPort = 8000,
    [int]$UiPort  = 8501,
    [switch]$Stop,        # derruba o que estiver escutando nas portas (em vez de subir)
    [switch]$NoBrowser    # não abre o navegador ao final (útil p/ automação/teste)
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot          # o script vive em scripts/ -> raiz é o pai
$py   = Join-Path $root ".venv\Scripts\python.exe"

function Get-PidOnPort([int]$port) {
    # PID do processo ESCUTANDO na porta (não conexões de cliente) — é o que sobe/derruba.
    (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1).OwningProcess
}

if ($Stop) {
    # Caminho de parada: mata pelo dono da porta (robusto a múltiplas execuções/janelas).
    foreach ($p in @($ApiPort, $UiPort)) {
        $owner = Get-PidOnPort $p
        if ($owner) { Stop-Process -Id $owner -Force -Confirm:$false; Write-Host "porta ${p}: processo $owner encerrado" }
        else        { Write-Host "porta ${p}: nada escutando" }
    }
    exit 0
}

# --- Pré-checagens com mensagens acionáveis (em vez de stack trace) ---
if (-not (Test-Path $py)) {
    Write-Host "ERRO: .venv não encontrada. Crie com:" -ForegroundColor Red
    Write-Host "  python -m venv .venv; .venv\Scripts\Activate.ps1; pip install -r requirements.txt"
    exit 1
}
if (-not (Test-Path (Join-Path $root ".env"))) {
    # Sem .env o sistema RODA (modo degradado/BM25-only) — avisamos, não bloqueamos.
    Write-Host "AVISO: .env não existe (copy .env.example .env). Subindo em modo degradado, sem LLM." -ForegroundColor Yellow
}
foreach ($p in @($ApiPort, $UiPort)) {
    if (Get-PidOnPort $p) {
        # Nunca subir por cima de um servidor existente: dois processos brigando pela mesma
        # porta gera erro confuso. Quem decide derrubar é o usuário (-Stop).
        Write-Host "ERRO: porta $p já está em uso. Rode com -Stop primeiro, ou use -ApiPort/-UiPort." -ForegroundColor Red
        exit 1
    }
}

# --- API (uvicorn) ---
Start-Process -FilePath $py -WorkingDirectory $root -WindowStyle Minimized `
    -ArgumentList "-m","uvicorn","app.api:app","--port","$ApiPort"

# --- UI (Streamlit) ---
# Filhos herdam o ambiente deste processo: é assim que a UI descobre a porta da API
# (Start-Process não tem parâmetro de env vars no PowerShell 5.1).
$env:API_BASE_URL = "http://127.0.0.1:$ApiPort"
Start-Process -FilePath $py -WorkingDirectory $root -WindowStyle Minimized `
    -ArgumentList "-m","streamlit","run","ui/streamlit_app.py",
                  "--server.port","$UiPort","--server.headless","true",
                  "--browser.gatherUsageStats","false"

# --- Espera ficar de pé (health real, não sleep cego) e abre o navegador ---
Write-Host "Subindo API (:$ApiPort) e UI (:$UiPort)..."
$apiOk = $false; $uiOk = $false
foreach ($i in 1..30) {
    try { $null = Invoke-RestMethod  -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2; $apiOk = $true } catch {}
    try { $null = Invoke-WebRequest -Uri "http://127.0.0.1:$UiPort" -TimeoutSec 2 -UseBasicParsing; $uiOk = $true } catch {}
    if ($apiOk -and $uiOk) { break }
    Start-Sleep -Seconds 2
}
if (-not ($apiOk -and $uiOk)) {
    Write-Host "ERRO: serviço não respondeu (API=$apiOk UI=$uiOk). Veja as janelas minimizadas p/ o log." -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "✅ Pronto!  UI: http://localhost:$UiPort   API: http://localhost:$ApiPort/health" -ForegroundColor Green
Write-Host "   (para derrubar: powershell -File scripts\run_local.ps1 -Stop)"
if (-not $NoBrowser) { Start-Process "http://localhost:$UiPort" }
