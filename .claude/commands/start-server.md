# Start Backend Server

Start the backend server using ./start-backend.sh and monitor logs for successful startup.

## Instructions

1. **Check if backend is already running:**
   - Run `lsof -ti:8000` to check for existing process
   - If running, ask user if they want to restart (kill and start fresh)

2. **Kill existing process if needed:**
   - Run `lsof -ti:8000 | xargs kill -9 2>/dev/null`
   - Wait 2 seconds for cleanup

3. **Start the backend:**
   - Navigate to project root: `/Users/karthi/Documents/AI\ Projects/UnizyVoice`
   - Run `./start-backend.sh` as a background process
   - The script activates venv and starts uvicorn

4. **Monitor startup:**
   - Wait 3-5 seconds for server to initialize
   - Check the background task output for startup messages
   - Look for these success indicators:
     - `Uvicorn running on http://0.0.0.0:8000`
     - `Application startup complete`
     - `Backend startup complete`

5. **Verify server is responding:**
   - Run `curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/docs"`
   - Expect HTTP 200 response

6. **Check for startup errors:**
   - Look for ERROR or Exception in startup logs
   - Common issues:
     - Port 8000 already in use
     - Missing environment variables
     - Import errors
     - Database connection failures

7. **Report status:**
   - If successful: Report server is running with PID
   - If failed: Show error logs and suggest fixes

## Output Format

```
## Backend Server Status

**Action:** Starting backend server...

### Startup Log
[Recent log output]

### Status
- **Process ID:** [PID]
- **Port:** 8000
- **Health Check:** [PASS/FAIL]
- **API Docs:** http://localhost:8000/docs

### Errors (if any)
[Error details and suggested fixes]
```

## Commands Reference

```bash
# Kill existing process
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Start backend (from project root)
cd /Users/karthi/Documents/AI\ Projects/UnizyVoice && ./start-backend.sh &

# Check if running
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/docs"
```
