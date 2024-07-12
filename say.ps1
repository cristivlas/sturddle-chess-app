param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$TextToSpeak
)

try {
    $voice = New-Object -ComObject SAPI.SpVoice
    $voice.Speak($TextToSpeak)
}
catch {
    Write-Error "An error occurred: $_"
}
finally {
    if ($voice) {
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($voice) | Out-Null
    }
}

# Explicitly return nothing
return $null