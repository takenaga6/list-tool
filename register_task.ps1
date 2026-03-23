$action  = New-ScheduledTaskAction -Execute "C:\Users\user\list_tool\start_daemon.bat"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = "PT1M"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask `
    -TaskName "ListTool_ListDaemon" `
    -Action   $action `
    -Trigger  $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force
Write-Host "Done"
