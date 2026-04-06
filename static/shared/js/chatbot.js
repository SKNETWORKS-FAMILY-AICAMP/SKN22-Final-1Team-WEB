/**
 * MirrAI Admin Chatbot Service
 * Handles UI interactions and API communication for the hair styling guide.
 */
(function () {
  'use strict';

  function getElements() {
    return {
      chatbotPanel: document.getElementById('chatbotPanel'),
      chatbotTrigger: document.getElementById('chatbotTrigger'),
      chatMessages: document.getElementById('chatMessages'),
      chatForm: document.getElementById('chatForm'),
      chatInput: document.getElementById('chatInput'),
      typingIndicator: document.getElementById('typingIndicator'),
      chatStartTime: document.getElementById('chatStartTime'),
    };
  }

  function init() {
    const {
      chatbotPanel,
      chatbotTrigger,
      chatForm,
      chatStartTime,
    } = getElements();

    if (!chatbotPanel || !chatbotTrigger || !chatForm) {
      return;
    }

    if (chatbotTrigger.dataset.chatbotBound === 'true') {
      return;
    }

    chatbotTrigger.addEventListener('click', window.toggleChatbot);
    chatForm.addEventListener('submit', handleChatSubmit);
    chatbotTrigger.dataset.chatbotBound = 'true';

    if (chatStartTime && !chatStartTime.textContent) {
      chatStartTime.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
  }

  window.initMirraiChatbot = init;

  window.toggleChatbot = function () {
    const { chatbotPanel, chatInput } = getElements();
    if (!chatbotPanel) {
      return;
    }

    chatbotPanel.classList.toggle('active');
    if (chatbotPanel.classList.contains('active') && chatInput) {
      chatInput.focus();
      scrollToBottom();
    }
  };

  window.sendQuickMessage = function (text) {
    const { chatInput } = getElements();
    if (!chatInput) {
      return;
    }

    chatInput.value = text;
    handleChatSubmit(new Event('submit'));
  };

  async function handleChatSubmit(e) {
    if (e) {
      e.preventDefault();
    }

    const { chatInput } = getElements();
    if (!chatInput) {
      return;
    }

    const message = chatInput.value.trim();
    if (!message) {
      return;
    }

    addMessage(message, 'user');
    chatInput.value = '';
    showTyping(true);
    scrollToBottom();

    try {
      const response = await fetch('/api/v1/admin/chatbot/ask/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({ message }),
      });

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('챗봇 API가 아직 준비되지 않았습니다. 백엔드 구현 상태를 확인해 주세요.');
        }
        throw new Error('서버 응답 오류가 발생했습니다.');
      }

      const data = await response.json();
      showTyping(false);
      addMessage(data.reply || data.message, 'bot');
    } catch (error) {
      console.error('Chatbot Error:', error);
      showTyping(false);
      addMessage(error.message || '죄송합니다. 통신 중 오류가 발생했습니다.', 'bot');
    }

    scrollToBottom();
  }

  function addMessage(text, side) {
    const { chatMessages } = getElements();
    if (!chatMessages) {
      return;
    }

    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${side}`;
    const formattedText = String(text || '').replace(/\n/g, '<br>');

    msgDiv.innerHTML = `
      ${formattedText}
      <span class="time">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
    `;
    chatMessages.appendChild(msgDiv);
  }

  function showTyping(show) {
    const { typingIndicator } = getElements();
    if (!typingIndicator) {
      return;
    }

    if (show) {
      typingIndicator.classList.remove('is-hidden');
    } else {
      typingIndicator.classList.add('is-hidden');
    }
  }

  function scrollToBottom() {
    const { chatMessages } = getElements();
    if (!chatMessages) {
      return;
    }

    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === `${name}=`) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
