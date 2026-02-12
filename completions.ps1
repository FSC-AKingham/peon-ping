# peon-ping PowerShell tab completion
Register-ArgumentCompleter -CommandName peon -ScriptBlock {
    param($commandName, $wordToComplete, $commandAst, $fakeBoundParameter)

    $opts = @('--pause', '--resume', '--toggle', '--status', '--packs', '--pack', '--help')

    # If previous word is --pack, complete with pack names
    $tokens = $commandAst.ToString() -split '\s+'
    if ($tokens.Count -ge 2 -and $tokens[-1] -eq '--pack' -and $wordToComplete -eq '') {
        $packsDir = Join-Path $env:USERPROFILE '.claude\hooks\peon-ping\packs'
        if (Test-Path $packsDir) {
            Get-ChildItem -Path $packsDir -Directory |
                Where-Object { Test-Path (Join-Path $_.FullName 'manifest.json') } |
                ForEach-Object {
                    [System.Management.Automation.CompletionResult]::new($_.Name, $_.Name, 'ParameterValue', $_.Name)
                }
        }
        return
    }

    $opts | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
    }
}
