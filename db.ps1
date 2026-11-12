# Start / stop / check the private PostgreSQL instance for Collab Pickup.
# The data lives in .pgdata next to this script and listens on port 5434.
# Usage: .\db.ps1 start | stop | status
param([ValidateSet("start", "stop", "status")][string]$cmd = "status")
$bin = "C:\Program Files\PostgreSQL\18\bin"
$data = Join-Path $PSScriptRoot ".pgdata"
$log = Join-Path $PSScriptRoot ".pgdata.log"
switch ($cmd) {
    "start"  { & "$bin\pg_ctl.exe" -D $data -l $log -o "-p 5434" -w start }
    "stop"   { & "$bin\pg_ctl.exe" -D $data -m fast -w stop }
    "status" { & "$bin\pg_ctl.exe" -D $data status }
}
