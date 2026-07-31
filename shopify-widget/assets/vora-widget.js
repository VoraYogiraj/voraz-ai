(function () {
  const API_URL = window.VORA_CONFIG?.apiUrl || '';
  let sessionToken = localStorage.getItem('vora_session');
  let photoSignalColors = [];
  let photoSignalSilhouettes = [];

  // ── Build widget HTML ──────────────────────────────────────────────
  document.body.insertAdjacentHTML('beforeend', `
    <button class="vw-trigger" id="vw-trigger" aria-label="Open VORA stylist">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path stroke-linecap="round" stroke-linejoin="round"
          d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25
             12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5
             0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/>
      </svg>
    </button>

    <div class="vw-panel" id="vw-panel" role="dialog" aria-label="VORA Bridal Stylist">
      <div class="vw-header">
        <span class="vw-logo">VORA</span>
        <span class="vw-subtitle">Your Bridal Stylist</span>
        <button class="vw-close" id="vw-close" aria-label="Close">✕</button>
      </div>

      <div class="vw-messages" id="vw-messages"></div>

      <div class="vw-photo-bar" id="vw-photo-bar" style="display:none">
        <label class="vw-photo-label" id="vw-photo-label">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
            <path stroke-linecap="round" stroke-linejoin="round"
              d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999
                 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0
                 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0
                 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0
                 00-1.736-1.039 48.776 48.776 0 00-5.232 0 2.192 2.192 0
                 00-1.736 1.039l-.821 1.316z"/>
            <path stroke-linecap="round" stroke-linejoin="round"
              d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z"/>
          </svg>
          Upload photo for personalised picks
          <input type="file" id="vw-photo-input" accept="image/*" style="display:none">
        </label>
      </div>

      <div class="vw-input-row">
        <input class="vw-input" id="vw-input" type="text"
               placeholder="Tell me about your dream look…" autocomplete="off">
        <button class="vw-send" id="vw-send" aria-label="Send">
          <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18">
            <path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75
                     0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94
                     60.519 60.519 0 0018.445-8.986.75.75 0
                     000-1.218A60.517 60.517 0 003.478 2.405z"/>
          </svg>
        </button>
      </div>
    </div>
  `);

  // ── Elements ───────────────────────────────────────────────────────
  const trigger   = document.getElementById('vw-trigger');
  const panel     = document.getElementById('vw-panel');
  const closeBtn  = document.getElementById('vw-close');
  const messages  = document.getElementById('vw-messages');
  const input     = document.getElementById('vw-input');
  const sendBtn   = document.getElementById('vw-send');
  const photoBar  = document.getElementById('vw-photo-bar');
  const photoInput= document.getElementById('vw-photo-input');

  // ── Open / close ───────────────────────────────────────────────────
  trigger.addEventListener('click', () => {
    panel.classList.add('vw-open');
    trigger.style.display = 'none';
    if (!messages.children.length) startConversation();
  });

  closeBtn.addEventListener('click', () => {
    panel.classList.remove('vw-open');
    trigger.style.display = '';
  });

  // ── Bubble helpers ─────────────────────────────────────────────────
  function addBubble(role, html, id) {
    const el = document.createElement('div');
    el.className = `vw-bubble vw-${role}`;
    if (id) el.id = id;
    el.innerHTML = html;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
    return el;
  }

  function removeById(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  function typingIndicator() {
    const id = 'vw-typing-' + Date.now();
    addBubble('ai', '<span class="vw-dot"></span><span class="vw-dot"></span><span class="vw-dot"></span>', id);
    return id;
  }

  // Format reply: bold **text**, line breaks, product links
  function formatReply(text) {
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>')
      .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">View →</a>');
  }

  // ── API calls ──────────────────────────────────────────────────────
  async function startConversation() {
    const tid = typingIndicator();
    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'Hi' }),
      });
      const data = await res.json();
      sessionToken = data.session_token;
      localStorage.setItem('vora_session', sessionToken);
      removeById(tid);
      addBubble('ai', formatReply(data.reply));
      maybeShowPhotoBar(data.stage);
    } catch {
      removeById(tid);
      addBubble('ai', 'Connection issue — please refresh and try again.');
    }
  }

  async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;
    addBubble('user', escHtml(text));
    input.value = '';
    const tid = typingIndicator();
    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_token: sessionToken, message: text }),
      });
      const data = await res.json();
      sessionToken = data.session_token;
      localStorage.setItem('vora_session', sessionToken);
      removeById(tid);
      addBubble('ai', formatReply(data.reply));
      maybeShowPhotoBar(data.stage);
    } catch {
      removeById(tid);
      addBubble('ai', "I'm having a connection issue. Please try again.");
    }
  }

  async function sendPhoto(file) {
    // Consent confirmation
    const consent = window.confirm(
      'VORA will analyse this photo to suggest colours and silhouettes suited to you. ' +
      'Your photo is stored securely and deleted after 30 days. Continue?'
    );
    if (!consent) return;

    addBubble('user', `📷 <em>${escHtml(file.name)}</em>`);
    const tid = typingIndicator();

    const form = new FormData();
    form.append('session_token', sessionToken);
    form.append('consent_given', 'true');
    form.append('photo', file);

    try {
      const res = await fetch(`${API_URL}/api/chat/photo`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json();
      removeById(tid);

      if (data.undertone_colors?.length) {
        photoSignalColors = data.undertone_colors;
        photoSignalSilhouettes = data.body_shape_silhouettes || [];
        addBubble('ai',
          `✨ Based on your photo, colours like <strong>${photoSignalColors.slice(0,3).join(', ')}</strong> ` +
          `will complement you beautifully` +
          (photoSignalSilhouettes.length
            ? ` — and silhouettes like <strong>${photoSignalSilhouettes[0]}</strong> tend to look stunning on your frame.`
            : '.') +
          `<br><br>Shall I now find lehengas that match?`
        );
      } else {
        addBubble('ai', data.reply || "Photo received! Let me find looks that suit you.");
      }
    } catch {
      removeById(tid);
      addBubble('ai', "Couldn't process the photo. You can continue without it.");
    }
  }

  // ── Photo bar visibility ───────────────────────────────────────────
  function maybeShowPhotoBar(stage) {
    if (stage === 'profiling' || stage === 'styling') {
      photoBar.style.display = '';
    }
  }

  // ── Event listeners ────────────────────────────────────────────────
  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keypress', e => { if (e.key === 'Enter') sendMessage(); });

  photoInput.addEventListener('change', () => {
    if (photoInput.files[0]) sendPhoto(photoInput.files[0]);
    photoInput.value = '';
  });

  // ── Util ───────────────────────────────────────────────────────────
  function escHtml(str) {
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
})();