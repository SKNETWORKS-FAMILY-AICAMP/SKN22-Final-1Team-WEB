/**
 * MirrAI Admin Chatbot Service
 * Handles UI interactions and API communication for the hair styling guide.
 */
(function () {
  'use strict';

  const chatbotPanel = document.getElementById('chatbotPanel');
  const chatbotTrigger = document.getElementById('chatbotTrigger');
  const chatMessages = document.getElementById('chatMessages');
  const chatForm = document.getElementById('chatForm');
  const chatInput = document.getElementById('chatInput');
  const typingIndicator = document.getElementById('typingIndicator');
  const chatStartTime = document.getElementById('chatStartTime');

  // Initialize
  function init() {
    if (!chatbotPanel || !chatbotTrigger) return;

    chatbotTrigger.addEventListener('click', toggleChatbot);
    chatForm.addEventListener('submit', handleChatSubmit);

    if (chatStartTime) {
      chatStartTime.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
  }

  window.toggleChatbot = function() {
    chatbotPanel.classList.toggle('active');
    if (chatbotPanel.classList.contains('active')) {
      chatInput.focus();
      scrollToBottom();
    }
  };

  window.sendQuickMessage = function(text) {
    chatInput.value = text;
    handleChatSubmit(new Event('submit'));
  };

  async function handleChatSubmit(e) {
    if (e) e.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;

    // Add user message to UI
    addMessage(message, 'user');
    chatInput.value = '';
    
    // Show typing indicator
    showTyping(true);
    scrollToBottom();

    try {
      // API call to backend (endpoint to be implemented)
      const response = await fetch('/api/v1/admin/chatbot/ask/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({ message: message })
      });

      if (!response.ok) {
          if (response.status === 404) throw new Error("챗봇 API가 아직 준비되지 않았습니다. (백엔드 구현 중)");
          throw new Error("서버 응답 오류");
      }

      const data = await response.json();
      showTyping(false);
      addMessage(data.reply || data.message, 'bot');

    } catch (error) {
      console.error('Chatbot Error:', error);
      showTyping(false);
      addMessage(error.message || "죄송합니다. 통신 중 오류가 발생했습니다.", 'bot');
    }
    
    scrollToBottom();
  }

  function addMessage(text, side) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${side}`;
    
    // Support for simple line breaks or markdown-like list
    const formattedText = text.replace(/\n/g, '<br>');
    
    msgDiv.innerHTML = `
      ${formattedText}
      <span class="time">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
    `;
    chatMessages.appendChild(msgDiv);
  }

  function showTyping(show) {
    if (show) typingIndicator.classList.remove('is-hidden');
    else typingIndicator.classList.add('is-hidden');
  }

  function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + "=")) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

})();
