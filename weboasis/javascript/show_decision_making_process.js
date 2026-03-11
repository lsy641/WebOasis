(([description, enableSpeech]) => {
    // Remove any existing decision-making overlays (both legacy and current IDs)
    let existing = document.getElementById('webagent-task-desc');
    if (existing) existing.remove();
    let legacy = document.getElementById('browsergym-task-desc');
    if (legacy) legacy.remove();

    let div = document.createElement('div');
    div.id = 'webagent-task-desc';
    div.setAttribute('developer_elem', ''); 
    div.innerText = description;
    div.style.position = 'fixed';
    div.style.top = '20px';
    div.style.left = '20px';
    div.style.maxWidth = '500px';
    div.style.width = 'auto';
    div.style.background = 'rgba(44, 62, 80, 0.8)';
    div.style.color = '#fff';
    div.style.padding = '8px 14px';
    div.style.borderRadius = '6px';
    div.style.fontSize = '10px';
    div.style.fontFamily = 'monospace';
    div.style.zIndex = 2147483647;
    div.style.boxShadow = '0 2px 12px rgba(0,0,0,0.15)';
    div.style.overflowWrap = 'break-word';
    div.style.wordBreak = 'break-word';
    div.style.whiteSpace = 'pre-line';
    document.body.appendChild(div);
    
    // Speech synthesis (optional)
    if (enableSpeech && 'speechSynthesis' in window) {
        // Cancel any ongoing speech
        window.speechSynthesis.cancel();
        const utter = new window.SpeechSynthesisUtterance(description);
        utter.rate = 1;
        utter.pitch = 1;
        utter.volume = 1;
        // Try to select a more natural voice
        const voices = window.speechSynthesis.getVoices();
        const preferredVoice = voices.find(v => v.name === 'Google US English') ||
                            voices.find(v => v.name === 'Samantha') ||
                            voices.find(v => v.lang === 'en-US');
        if (preferredVoice) {
            utter.voice = preferredVoice;
        }
        // Optionally, set language: utter.lang = 'en-US';
        utter.lang = 'en-US';
        window.speechSynthesis.speak(utter);
    }
})