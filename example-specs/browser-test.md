# Simple Web Application for Browser Testing

Create a minimal web application to test agent-browser integration.

## Requirements

1. **Simple Express Backend** (port 3001)
   - GET /api/health - Returns { status: "ok", timestamp: Date.now() }
   - GET /api/message - Returns { message: "Hello from the server!" }

2. **Simple Frontend** (port 5173)
   - Single HTML page with:
     - Title: "Browser Test"
     - H1: "Testing Browser Automation"
     - Button: "Test API" that fetches /api/message
     - Div to display the API response
   - Should log to console: "Page loaded successfully"

3. **Project Structure**
   - server/index.js - Express server
   - frontend/index.html - Simple HTML page
   - frontend/script.js - JavaScript for API interaction
   - init.sh - Script to start both servers

## Testing Requirements

After implementation, verify with browser automation that:
- Frontend loads without errors
- API health check returns 200
- Button click fetches and displays message
- Console has no errors

This is designed to test agent-browser browser automation.
