@echo off
:: Launch Claude Code as the read-only "skynet" user, in THIS desktop session.
::
:: skynet never logs in.  runas creates a token and one process; that process
:: inherits the machine-level env vars (%code% %kpy% %db% %data%), uses the
:: shared repo, and maps B: with skynet's own read-only NAS credential.
::
:: /savecred: the skynet password is asked once, then stored by Windows.
:: (Requires Pro/Education edition -- kong is Education.)
::
:: First run only, inside the skynet window before this works unattended:
::   cmdkey /add:bananastand.physics.ucsb.edu /user:skynet /pass
::   (enter the NAS password for skynet once)

set SKYNET_CMD=^
net use B: \\bananastand.physics.ucsb.edu\anewstart /persistent:no ^>nul 2^>^&1 ^& ^
set CLAUDE_CONFIG_DIR=C:\Users\jarjarbinks\.claude ^& ^
cd /d %code% ^& ^
call %kpy% ^& ^
claude

runas /savecred /user:skynet "cmd /k %SKYNET_CMD%"
