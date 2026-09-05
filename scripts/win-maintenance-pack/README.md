# Windows Maintenance Pack

Prevents a repeat of the July 2026 incident (a cumulative update installed onto a
corrupt component store overnight and broke networking on two machines).

## What it sets up

1. **Auto-updates OFF (policy)** — Windows Update becomes notify-only
   (`AUOptions=2`): it checks and shows updates but installs nothing on its own.
   `NoAutoRebootWithLoggedOnUsers=1` means it can never reboot a logged-in session.
2. **`WindowsHealthCheck-Monthly`** — 5th of each month, 03:30: DISM ScanHealth +
   SFC /scannow. Posts green/red one-liner to Discord #alerts.
3. **`WindowsUpdate-Monthly`** — 16th of each month, 10:00 (daytime, after Patch
   Tuesday): installs all pending updates via PSWindowsUpdate. **Safety gate**:
   refuses to install if the last health check found corruption. Posts progress +
   results to #alerts. Never auto-reboots — it asks for a same-day reboot instead.

Monthly rhythm: 5th = health check -> 8th-14th = Patch Tuesday (nothing installs)
-> 16th = deliberate daytime install on a verified-clean store.

## Install (laptop, after the Windows restore completes)

1. Copy this whole folder to the laptop (USB or OneDrive).
2. Right-click `install.ps1` -> "Run with PowerShell" (it self-elevates; approve UAC).
3. It finishes by launching a first health check (~10-20 min) — watch #alerts for
   the result. If it's red, run `dism /online /cleanup-image /restorehealth`
   elevated, then re-run the health check before letting any updates install.

`webhook.txt` contains the #alerts Discord webhook (secret — don't share the
folder). The installer converts it to `C:\ProgramData\WindowsMaintenance\config.json`.

## On demand

- Install updates now (elevated): `Start-ScheduledTask WindowsUpdate-Monthly`
- Run health check now (elevated): `Start-ScheduledTask WindowsHealthCheck-Monthly`
- Logs: `C:\ProgramData\WindowsMaintenance\logs\`

## Note

The desktop already runs the same setup (installed 16 Jul 2026), with the scripts
living in the discord-messenger repo (`scripts/windows-health-check.ps1` /
`windows-update-monthly.ps1`) instead of ProgramData. This pack is the portable
equivalent; installing it on the desktop too would be harmless but redundant.
