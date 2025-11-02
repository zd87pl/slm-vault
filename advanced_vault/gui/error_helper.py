"""
Error Message Helper

Converts technical errors to user-friendly messages with contextual help.
"""

from typing import Optional, Dict, Tuple
import re

# Error pattern mappings: (pattern, user_message, help_link)
ERROR_PATTERNS = [
    # Network errors
    (r"Connection.*refused|Failed to connect|ECONNREFUSED", 
     "Couldn't connect to the server. Check your internet connection and try again.",
     "https://docs.enclave.ai/troubleshooting/connection-issues"),
    
    (r"Timeout|timed out|ETIMEDOUT",
     "Request timed out. The server is taking too long to respond. Please try again.",
     "https://docs.enclave.ai/troubleshooting/timeout-errors"),
    
    (r"SSL|TLS|certificate|SSL.*error",
     "Security connection error. Please check your system time and try again.",
     "https://docs.enclave.ai/troubleshooting/ssl-errors"),
    
    # Authentication errors
    (r"401|Unauthorized|invalid.*token|expired.*token|authentication.*failed",
     "Your session has expired. Please log out and log back in.",
     "https://docs.enclave.ai/troubleshooting/authentication"),
    
    (r"403|Forbidden|permission.*denied|access.*denied",
     "You don't have permission to perform this action. Please contact support if you believe this is an error.",
     "https://docs.enclave.ai/troubleshooting/permissions"),
    
    # Server errors
    (r"500|Internal.*error|server.*error",
     "The server encountered an error. Your data is safe - try again in a few moments.",
     "https://docs.enclave.ai/troubleshooting/server-errors"),
    
    (r"503|Service.*unavailable|maintenance",
     "The service is temporarily unavailable. Please try again in a few minutes.",
     "https://docs.enclave.ai/troubleshooting/service-unavailable"),
    
    (r"502|Bad.*gateway|proxy.*error",
     "Service is temporarily unavailable. Please try again shortly.",
     "https://docs.enclave.ai/troubleshooting/gateway-errors"),
    
    # Training errors
    (r"training.*not.*configured|RunPod.*not.*configured",
     "Training service is not available. Please contact support to enable training.",
     "https://docs.enclave.ai/troubleshooting/training-unavailable"),
    
    (r"dataset.*not.*found|file.*not.*found|FileNotFoundError",
     "File not found. Please ensure the file exists and try again.",
     None),
    
    (r"failed.*to.*upload|upload.*failed",
     "Failed to upload file. Check your connection and file size, then try again.",
     "https://docs.enclave.ai/troubleshooting/upload-errors"),
    
    # Vault errors
    (r"vault.*not.*initialized|key.*not.*found|master.*key",
     "Vault encryption error. Please restart the app. Your data is safe.",
     "https://docs.enclave.ai/troubleshooting/vault-errors"),
    
    (r"decryption.*failed|encryption.*failed|cipher.*error",
     "Encryption error. Please ensure your vault key is intact and try again.",
     "https://docs.enclave.ai/troubleshooting/encryption-errors"),
    
    # Generic patterns
    (r"not.*found|404",
     "Resource not found. It may have been deleted or moved.",
     None),
    
    (r"validation.*error|invalid.*input|bad.*request",
     "Invalid input. Please check your data and try again.",
     None),
    
    (r"rate.*limit|too.*many.*requests|429",
     "Too many requests. Please wait a moment and try again.",
     "https://docs.enclave.ai/troubleshooting/rate-limiting"),
]


def make_user_friendly(error_message: str, context: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    Convert technical error message to user-friendly format.
    
    Args:
        error_message: Original technical error message
        context: Optional context (e.g., "training", "upload", "sync")
        
    Returns:
        Tuple of (user_friendly_message, help_link)
    """
    if not error_message:
        return "An unexpected error occurred. Please try again.", None
    
    error_lower = error_message.lower()
    
    # Check against patterns
    for pattern, user_msg, help_link in ERROR_PATTERNS:
        if re.search(pattern, error_lower, re.IGNORECASE):
            # Add context if provided
            if context:
                context_msgs = {
                    "training": "Training: ",
                    "upload": "Upload: ",
                    "sync": "Sync: ",
                    "auth": "Authentication: ",
                }
                prefix = context_msgs.get(context, "")
                return f"{prefix}{user_msg}", help_link
            return user_msg, help_link
    
    # If no pattern matches, provide generic friendly message
    # But try to extract useful info from technical error
    if ":" in error_message:
        # Often technical errors have format "ErrorType: message"
        parts = error_message.split(":", 1)
        if len(parts) > 1:
            # Use the second part (the actual message) if it's readable
            message_part = parts[1].strip()
            if len(message_part) < 100 and not any(char.isupper() for char in message_part[:10]):
                return f"An error occurred: {message_part}", None
    
    # Fallback: generic message
    return "Something went wrong. Please try again. If the problem persists, contact support.", None


def format_error_dialog(title: str, message: str, help_link: Optional[str] = None) -> Dict:
    """
    Format error for display in dialog.
    
    Returns:
        Dict with title, content, and actions
    """
    content_items = [message]
    
    if help_link:
        content_items.append("\n\n")
        content_items.append(f"Need help? Visit: {help_link}")
    
    return {
        "title": title,
        "content": "".join(content_items) if isinstance(content_items[0], str) else content_items,
        "help_link": help_link
    }


def format_error_snackbar(message: str, help_link: Optional[str] = None) -> str:
    """
    Format error for display in snackbar (short format).
    
    Returns:
        User-friendly error message
    """
    # Snackbars should be short - truncate if needed
    if len(message) > 100:
        message = message[:97] + "..."
    
    return message

