/**
 * Consent Dialog Logic
 */

// Parse URL parameters
const params = new URLSearchParams(window.location.search);
const requestId = params.get('requestId');
const agentIdentifier = params.get('agentIdentifier');
const service = params.get('service');
const toolName = params.get('toolName');
const queryPreview = params.get('queryPreview');

// Populate UI
document.getElementById('agent-name').textContent = agentIdentifier || 'Unknown';
document.getElementById('service-name').textContent = service || 'All services';
document.getElementById('tool-name').textContent = toolName || 'vault_recall';

if (queryPreview) {
  document.getElementById('query-row').style.display = 'flex';
  document.getElementById('query-preview').textContent = queryPreview;
}

// Handle button clicks
document.getElementById('deny-btn').addEventListener('click', () => {
  sendDecision('deny');
});

document.getElementById('deny-always-btn').addEventListener('click', () => {
  if (confirm('This will permanently deny access for this agent. Continue?')) {
    sendDecision('deny_always');
  }
});

document.getElementById('allow-btn').addEventListener('click', () => {
  sendDecision('allow_once');
});

document.getElementById('allow-always-btn').addEventListener('click', () => {
  if (confirm('This will allow access for all future requests from this agent. Continue?')) {
    sendDecision('allow_always');
  }
});

function sendDecision(decision) {
  // Send decision to background script
  chrome.runtime.sendMessage({
    type: 'consent_decision',
    requestId,
    decision
  }, (response) => {
    // Close window after sending (or on error)
    setTimeout(() => {
      window.close();
    }, 100);
  });
}

// Handle keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    sendDecision('deny');
  }
});

