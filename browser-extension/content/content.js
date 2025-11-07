/**
 * Content Script
 * 
 * Optional: Detects API key inputs and suggests saving to vault.
 * Non-invasive - only observes, doesn't interfere.
 */

// Configuration: Known API key patterns
const API_KEY_PATTERNS = [
  /^sk-[a-zA-Z0-9]{32,}$/,  // OpenAI
  /^sk_live_[a-zA-Z0-9]{24,}$/,  // Stripe
  /^ghp_[a-zA-Z0-9]{36,}$/,  // GitHub
  /^xox[baprs]-[0-9a-zA-Z-]{10,48}$/,  // Slack
];

// Known service names for common domains
const SERVICE_MAPPINGS = {
  'openai.com': 'openai',
  'anthropic.com': 'anthropic',
  'github.com': 'github',
  'stripe.com': 'stripe',
  'slack.com': 'slack',
};

/**
 * Detect if input value looks like an API key
 */
function looksLikeApiKey(value) {
  if (!value || value.length < 20) return false;
  
  return API_KEY_PATTERNS.some(pattern => pattern.test(value));
}

/**
 * Get service name from current domain
 */
function getServiceFromDomain() {
  const hostname = window.location.hostname;
  for (const [domain, service] of Object.entries(SERVICE_MAPPINGS)) {
    if (hostname.includes(domain)) {
      return service;
    }
  }
  return null;
}

/**
 * Show suggestion to save API key
 */
function showSaveSuggestion(input, value) {
  // Check if already shown
  if (input.dataset.enclaveSuggestionShown) return;
  input.dataset.enclaveSuggestionShown = 'true';

  // Create suggestion badge
  const badge = document.createElement('div');
  badge.className = 'enclave-save-suggestion';
  badge.innerHTML = `
    <span>💡 Save to Enclave?</span>
    <button class="enclave-save-btn">Save</button>
  `;
  badge.style.cssText = `
    position: absolute;
    top: -32px;
    right: 0;
    background: white;
    border: 1px solid #1976d2;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    z-index: 10000;
  `;

  // Position relative to input
  const inputParent = input.parentElement;
  if (getComputedStyle(inputParent).position === 'static') {
    inputParent.style.position = 'relative';
  }
  inputParent.appendChild(badge);

  // Handle save button click
  badge.querySelector('.enclave-save-btn').addEventListener('click', async () => {
    const service = getServiceFromDomain() || 'unknown';
    
    // Send message to background script
    chrome.runtime.sendMessage({
      type: 'suggest_save_secret',
      service,
      value: value.substring(0, 20) + '...' // Only send preview
    }, (response) => {
      if (response && response.success) {
        badge.innerHTML = '<span>✓ Saved!</span>';
        setTimeout(() => badge.remove(), 2000);
      } else {
        badge.innerHTML = '<span>❌ Failed</span>';
        setTimeout(() => badge.remove(), 2000);
      }
    });
  });

  // Auto-hide after 5 seconds
  setTimeout(() => {
    if (badge.parentElement) {
      badge.remove();
    }
  }, 5000);
}

/**
 * Observe input fields for API keys
 */
function observeInputs() {
  // Watch for input events
  document.addEventListener('input', (e) => {
    if (e.target.tagName === 'INPUT' && e.target.type === 'password') {
      const value = e.target.value;
      if (looksLikeApiKey(value)) {
        showSaveSuggestion(e.target, value);
      }
    }
  }, true);

  // Also check existing password inputs
  document.querySelectorAll('input[type="password"]').forEach(input => {
    if (input.value && looksLikeApiKey(input.value)) {
      showSaveSuggestion(input, input.value);
    }
  });
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', observeInputs);
} else {
  observeInputs();
}

// Watch for dynamically added inputs
const observer = new MutationObserver(() => {
  document.querySelectorAll('input[type="password"]').forEach(input => {
    if (!input.dataset.enclaveObserved) {
      input.dataset.enclaveObserved = 'true';
      input.addEventListener('input', (e) => {
        if (looksLikeApiKey(e.target.value)) {
          showSaveSuggestion(e.target, e.target.value);
        }
      });
    }
  });
});

observer.observe(document.body, {
  childList: true,
  subtree: true
});

console.log('Enclave content script loaded');

