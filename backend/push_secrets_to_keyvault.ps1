$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
$ErrorActionPreference = "Stop"

$envFile = Join-Path $PSScriptRoot ".env"
$vars = @{}
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $parts = $_ -split '=', 2
    $key = $parts[0].Trim()
    $val = $parts[1].Trim()
    if ($key -and $val) { $vars[$key] = $val }
}

$secretMap = @{
    "azure-openai-endpoint"   = "AZURE_OPENAI_ENDPOINT"
    "azure-openai-api-key"    = "AZURE_OPENAI_API_KEY"
    "azure-search-endpoint"   = "AZURE_SEARCH_ENDPOINT"
    "azure-search-key"        = "AZURE_SEARCH_KEY"
    "azure-docintel-endpoint" = "AZURE_DOCINTEL_ENDPOINT"
    "azure-docintel-key"      = "AZURE_DOCINTEL_KEY"
    "azure-language-endpoint" = "AZURE_LANGUAGE_ENDPOINT"
    "azure-language-key"      = "AZURE_LANGUAGE_KEY"
    "appinsights-connection-string" = "AZURE_APPINSIGHTS_CONNECTION_STRING"
    "azure-contentsafety-endpoint"  = "AZURE_CONTENTSAFETY_ENDPOINT"
    "azure-contentsafety-key"       = "AZURE_CONTENTSAFETY_KEY"
}

foreach ($secretName in $secretMap.Keys) {
    $envKey = $secretMap[$secretName]
    if ($vars.ContainsKey($envKey)) {
        $tmpFile = [System.IO.Path]::GetTempFileName()
        [System.IO.File]::WriteAllText($tmpFile, $vars[$envKey], [System.Text.UTF8Encoding]::new($false))
        az keyvault secret set --vault-name filingsiq-kv --name $secretName --file $tmpFile --output none
        Remove-Item $tmpFile -Force
        Write-Host "Pushed secret: $secretName"
    }
}
Write-Host "All secrets pushed to Key Vault."
