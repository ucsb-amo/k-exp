@echo off
:: One-way mirror of the agent's local log folder into the shared Google Drive.
:: Runs under jarjarbinks (who has G:), on a Task Scheduler interval.
::
:: Deliberately NOT /MIR and NOT /PURGE: nothing is ever deleted on G:.
:: Files pruned locally stay on G: as history; a person cleans those up.
::   /E   all subfolders (logs + outputs)
::   /XO  skip files that are older than the copy already on G:
::   /XJ  do not follow junctions

robocopy "C:\lab\skynet_log" "G:\Shared drives\Tweezers\Other\skynet_log" /E /XO /XJ /R:1 /W:1 /NP /NDL /NJH /NJS /LOG+:"C:\lab\skynet_log_sync.log"
:: robocopy exit codes 0-7 are success variants; only >=8 is failure
if %ERRORLEVEL% GEQ 8 exit /b %ERRORLEVEL%
exit /b 0
