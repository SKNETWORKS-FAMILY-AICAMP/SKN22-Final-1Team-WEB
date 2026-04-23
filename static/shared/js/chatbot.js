/**
 * MirrAI Chatbot Service
 * Supports designer-only chatbot and customer trend chatbot with page-level configuration.
 */
(function () {
  'use strict';

  const DESIGNER_DEFAULT_PROMPTS = [
    { label: 'C컬 시술 순서', message: 'C컬 시술 순서를 알려줘' },
    { label: '염색 전 주의사항', message: '염색 전 주의사항을 알려줘' },
    { label: '레이어드 컷 가이드', message: '레이어드 컷 가이드를 알려줘' },
  ];

  function getChatbotRoots(target) {
    if (target && target.nodeType === 1 && target.matches('[data-chatbot-component]')) {
      return [target];
    }
    return Array.from(document.querySelectorAll('[data-chatbot-component]'));
  }

  function getElements(root) {
    return {
      panel: root.querySelector('[data-chatbot-panel]'),
      trigger: root.querySelector('[data-chatbot-trigger]'),
      close: root.querySelector('[data-chatbot-close]'),
      messages: root.querySelector('[data-chatbot-messages]'),
      form: root.querySelector('[data-chatbot-form]'),
      input: root.querySelector('[data-chatbot-input]'),
      typing: root.querySelector('[data-chatbot-typing]'),
      startTime: root.querySelector('[data-chatbot-start-time]'),
      quickPrompts: root.querySelector('[data-chatbot-quick-prompts]'),
    };
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      '\'': '&#39;',
    }[char]));
  }

  function normalizeDisplayText(value) {
    return String(value ?? '')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .replace(/\\n/g, '\n');
  }

  function parseQuickPrompts(root) {
    const raw = String(root.dataset.chatbotQuickPrompts || '').trim();
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          return parsed.filter((item) => item && item.label && item.message);
        }
      } catch (error) {
        console.warn('Failed to parse chatbot quick prompts:', error);
      }
    }

    const endpoint = String(root.dataset.chatbotEndpoint || '').trim();
    if (endpoint === '/api/v1/admin/chatbot/ask/') {
      return DESIGNER_DEFAULT_PROMPTS;
    }
    return [];
  }

  function normalizeChatbotResponse(data) {
    if (!data || typeof data !== 'object') {
      return {};
    }

    const nestedPayload = data.data || data.payload || data.result || null;
    if (nestedPayload && typeof nestedPayload === 'object') {
      return nestedPayload;
    }
    return data;
  }

  function getCookie(name) {
    const escapedName = name.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&');
    const match = document.cookie.match(new RegExp(`(?:^|; )${escapedName}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : '';
  }

  function scrollToBottom(root) {
    const { messages } = getElements(root);
    if (!messages) {
      return;
    }

    requestAnimationFrame(() => {
      messages.scrollTop = messages.scrollHeight;
    });
  }

  function showTyping(root, show) {
    const { typing } = getElements(root);
    if (!typing) {
      return;
    }
    typing.classList.toggle('is-hidden', !show);
  }

  function setPanelOpen(root, shouldOpen) {
    const { panel, input } = getElements(root);
    if (!panel) {
      return;
    }

    panel.classList.toggle('active', Boolean(shouldOpen));
    if (shouldOpen) {
      if (input) {
        input.focus();
      }
      scrollToBottom(root);
    }
  }

  function togglePanel(root) {
    const { panel } = getElements(root);
    if (!panel) {
      return;
    }
    setPanelOpen(root, !panel.classList.contains('active'));
  }

  function buildAttachmentCard(image) {
    const title = escapeHtml(image.title || '참고 이미지');
    const caption = String(image.caption || '').trim();
    const figure = String(image.figure || '').trim();
    const sourcePdf = String(image.source_pdf || '').trim();
    const page = image.page ? `p.${image.page}` : '';
    const meta = [figure, sourcePdf, page].filter(Boolean).join(' · ');
    const href = escapeHtml(image.url || '#');

    return `
      <a class="chatbot-attachment-card" href="${href}" target="_blank" rel="noopener noreferrer">
        <img class="chatbot-attachment-thumb" src="${href}" alt="${title}" loading="lazy">
        <div class="chatbot-attachment-title">${title}</div>
        ${caption ? `<div class="chatbot-attachment-caption">${escapeHtml(caption)}</div>` : ''}
        ${meta ? `<div class="chatbot-attachment-meta">${escapeHtml(meta)}</div>` : ''}
      </a>
    `;
  }

  function addMessage(root, { text, side, images }) {
    const { messages } = getElements(root);
    if (!messages) {
      return;
    }

    const messageNode = document.createElement('div');
    messageNode.className = `message ${side}`;
    const rawText = normalizeDisplayText(text).trim();
    messageNode.dataset.role = side === 'user' ? 'user' : 'bot';
    messageNode.dataset.messageText = rawText;

    const bodyNode = document.createElement('div');
    bodyNode.className = 'message-body';
    bodyNode.innerHTML = escapeHtml(rawText).replace(/\n/g, '<br>');
    messageNode.appendChild(bodyNode);

    if (Array.isArray(images) && images.length) {
      const attachmentNode = document.createElement('div');
      attachmentNode.className = 'chatbot-attachment-grid';
      attachmentNode.innerHTML = images
        .filter((item) => item && item.url)
        .map((item) => buildAttachmentCard(item))
        .join('');
      if (attachmentNode.innerHTML.trim()) {
        messageNode.appendChild(attachmentNode);
      }
    }

    const timeNode = document.createElement('span');
    timeNode.className = 'time';
    timeNode.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    messageNode.appendChild(timeNode);

    messages.appendChild(messageNode);
    scrollToBottom(root);
  }

  function collectConversationHistory(root) {
    const { messages } = getElements(root);
    if (!messages) {
      return [];
    }

    return Array.from(messages.querySelectorAll('.message'))
      .map((node) => {
        const content = String(node.dataset.messageText || '').trim();
        if (!content) {
          return null;
        }
        return {
          role: node.dataset.role === 'user' ? 'user' : 'bot',
          content,
        };
      })
      .filter(Boolean)
      .slice(-8);
  }

  function renderQuickPrompts(root) {
    const { quickPrompts } = getElements(root);
    if (!quickPrompts) {
      return;
    }

    const prompts = parseQuickPrompts(root);
    quickPrompts.innerHTML = '';

    prompts.forEach((item) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'chatbot-quick-prompt';
      button.textContent = item.label;
      button.addEventListener('click', () => {
        const { input } = getElements(root);
        if (!input) {
          return;
        }
        input.value = item.message;
        void submitMessage(root);
      });
      quickPrompts.appendChild(button);
    });
  }

  async function submitMessage(root, event) {
    if (event) {
      event.preventDefault();
    }

    const { input } = getElements(root);
    if (!input) {
      return;
    }

    const endpoint = String(root.dataset.chatbotEndpoint || '').trim();
    const message = input.value.trim();
    if (!endpoint || !message) {
      return;
    }

    const conversationHistory = collectConversationHistory(root);
    addMessage(root, { text: message, side: 'user', images: [] });
    input.value = '';
    showTyping(root, true);

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({
          message,
          conversation_history: conversationHistory,
        }),
      });

      const rawData = await response.json();
      const payload = normalizeChatbotResponse(rawData);
      if (!response.ok) {
        throw new Error(payload.detail || payload.message || '서버 응답 오류가 발생했습니다.');
      }

      addMessage(root, {
        text: payload.reply || payload.message || '답변을 불러오지 못했습니다.',
        side: 'bot',
        images: payload.images || [],
      });
    } catch (error) {
      console.error('Chatbot Error:', error);
      addMessage(root, {
        text: error.message || '죄송합니다. 통신 중 오류가 발생했습니다.',
        side: 'bot',
        images: [],
      });
    } finally {
      showTyping(root, false);
    }
  }

  function initRoot(root) {
    const elements = getElements(root);
    if (!elements.panel || !elements.trigger || !elements.form || !elements.messages) {
      return;
    }

    elements.messages.querySelectorAll('.message').forEach((node) => {
      const normalizedText = normalizeDisplayText(node.dataset.messageText || '').trim();
      node.dataset.messageText = normalizedText;
      const bodyNode = node.querySelector('.message-body');
      if (bodyNode) {
        bodyNode.innerHTML = escapeHtml(normalizedText).replace(/\n/g, '<br>');
      }
    });

    renderQuickPrompts(root);

    if (root.dataset.chatbotBound === 'true') {
      return;
    }

    elements.trigger.addEventListener('click', () => togglePanel(root));
    if (elements.close) {
      elements.close.addEventListener('click', () => setPanelOpen(root, false));
    }
    elements.form.addEventListener('submit', (event) => {
      void submitMessage(root, event);
    });

    if (elements.startTime && !elements.startTime.textContent) {
      elements.startTime.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    root.dataset.chatbotBound = 'true';
  }

  function init(target) {
    getChatbotRoots(target).forEach((root) => {
      initRoot(root);
    });
  }

  window.initMirraiChatbot = init;
  window.openMirraiChatbot = function () {
    const root = document.querySelector('[data-chatbot-component]');
    if (!root) {
      return;
    }
    initRoot(root);
    setPanelOpen(root, true);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => init());
  } else {
    init();
  }
})();
