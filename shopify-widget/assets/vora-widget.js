(function() {
    const API_URL = window.VORA_CONFIG.apiUrl;
    let sessionToken = localStorage.getItem('vora_session');

    // 1. Create Widget HTML
    const widgetHTML = `
        <div class="vw-trigger" id="vora-trigger">
            <svg viewBox="0 0 24 24"><path d="M12 2L4.5 20.29L5.21 21L12 18L18.79 21L19.5 20.29L12 2Z"/></svg>
        </div>
        <div class="vw-container" id="vora-container">
            <div class="vw-header"><h3>VORA AI STYLIST</h3></div>
            <div class="vw-messages" id="vora-messages">
                <div class="vw-bubble ai">Namaste! 🌸 I am Vora, your personal bridal stylist. Which occasion are we dressing for today?</div>
            </div>
            <div class="vw-input-row">
                <input type="text" id="vora-input" placeholder="Type your vibe...">
                <button id="vora-send" style="background:none; border:none; color:#c9a96e; cursor:pointer;">Send</button>
            </div>
        </div>
    `;
    document.body.insertAdjacentHTML('beforeend', widgetHTML);

    // 2. Elements
    const trigger = document.getElementById('vora-trigger');
    const container = document.getElementById('vora-container');
    const messages = document.getElementById('vora-messages');
    const input = document.getElementById('vora-input');
    const sendBtn = document.getElementById('vora-send');

    // 3. Toggle Open/Close
    trigger.onclick = () => container.classList.toggle('active');

    // 4. Send Message Function
    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        // Add User Bubble
        addBubble('user', text);
        input.value = '';

        // Typing indicator
        const loadingId = addBubble('ai', 'Thinking...');

        try {
            const res = await fetch(`${API_URL}/api/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_token: sessionToken, message: text })
            });
            const data = await res.json();
            
            // Save session
            sessionToken = data.session_token;
            localStorage.setItem('vora_session', sessionToken);

            // Remove loading and add AI reply
            document.getElementById(loadingId).remove();
            addBubble('ai', data.reply);
        } catch (e) {
            addBubble('ai', "I'm having a connection issue. Please try again.");
        }
    }

    function addBubble(role, text) {
        const id = 'msg-' + Date.now();
        const html = `<div class="vw-bubble ${role}" id="${id}">${text}</div>`;
        messages.insertAdjacentHTML('beforeend', html);
        messages.scrollTop = messages.scrollHeight;
        return id;
    }

    sendBtn.onclick = sendMessage;
    input.onkeypress = (e) => { if(e.key === 'Enter') sendMessage(); };
})();