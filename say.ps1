param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$TextToSpeak
)

try {
    $voice = New-Object -ComObject SAPI.SpVoice

    # Get all available voices
    $voices = $voice.GetVoices()

    # Find an English voice
    $englishVoice = $voices | Where-Object { $_.GetAttribute("Language") -eq "409" } | Select-Object -First 1

    if ($englishVoice) {
        # Set the voice to the English one we found
        $voice.Voice = $englishVoice
        $voice.Speak($TextToSpeak)
        [System.Environment]::Exit(0)  # Explicit exit with 0 for success
    } else {
        Write-Error "No English voice found on the system."
        [System.Environment]::Exit(1)  # Explicit exit with 1 for "No English voice found"
    }
}
catch {
    Write-Error "An error occurred: $_"
    [System.Environment]::Exit(2)  # Explicit exit with 2 for general error
}
finally {
    if ($voice) {
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($voice) | Out-Null
    }
}