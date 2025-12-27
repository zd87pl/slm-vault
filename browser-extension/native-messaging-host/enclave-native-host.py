#!/usr/bin/env python3
"""
Enclave Native Messaging Host

Bridges communication between MCP server and browser extension.
Reads JSON-RPC messages from stdin and forwards them to the extension.
"""

import sys
import json
import struct
import subprocess
import os

def send_message(message):
    """Send message to extension via native messaging."""
    # Get extension ID from environment or config
    extension_id = os.environ.get('ENCLAVE_EXTENSION_ID', 'YOUR_EXTENSION_ID_HERE')
    
    # Use Chrome's native messaging API
    # For now, we'll use a simple approach: write to a named pipe or use HTTP
    # In production, this would use Chrome's native messaging protocol
    
    # POC: Use HTTP server approach (extension listens on localhost)
    # Or use stdin/stdout for direct communication
    
    # For now, return success
    return {
        "success": True,
        "message": "Native messaging not fully implemented yet. Use extension's HTTP endpoint for POC."
    }

def read_message():
    """Read a message from stdin (JSON-RPC format)."""
    # Read message length (4 bytes, little-endian)
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length:
        return None
    
    message_length = struct.unpack('=I', raw_length)[0]
    
    # Read the message itself
    message = sys.stdin.buffer.read(message_length).decode('utf-8')
    return json.loads(message)

def write_message(message):
    """Write a message to stdout (JSON-RPC format)."""
    message_json = json.dumps(message)
    message_bytes = message_json.encode('utf-8')
    
    # Write message length (4 bytes, little-endian)
    sys.stdout.buffer.write(struct.pack('=I', len(message_bytes)))
    sys.stdout.buffer.write(message_bytes)
    sys.stdout.buffer.flush()

def main():
    """Main message loop."""
    while True:
        try:
            # Read message from MCP server
            message = read_message()
            if message is None:
                break
            
            # Handle message
            if message.get('method') == 'consent_request':
                # Forward to extension
                result = send_message(message)
                
                # Send response back to MCP server
                response = {
                    "jsonrpc": "2.0",
                    "id": message.get('id'),
                    "result": result
                }
                write_message(response)
            else:
                # Unknown method
                response = {
                    "jsonrpc": "2.0",
                    "id": message.get('id'),
                    "error": {
                        "code": -32601,
                        "message": "Method not found"
                    }
                }
                write_message(response)
                
        except Exception as e:
            # Send error response
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }
            write_message(error_response)
            break

if __name__ == '__main__':
    main()



