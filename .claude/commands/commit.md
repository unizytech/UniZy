# Commit and Push to Git Remote

Commit all local changes and push to git remote with comprehensive pre-commit checks.

## Pre-Commit Checklist

Before committing, perform ALL of the following checks and get user approval:

### Check 1: Branch Verification
- Run `git branch --show-current` to verify current branch
- **MUST be on `dev` branch**
- If NOT on dev: **STOP** and warn user, ask if they want to switch or abort

### Check 2: Supabase Migration Sync
- Check if any migration files are staged: `git diff --cached --name-only | grep -E "supabase/migrations/.*\.sql$"`
- If migrations found:
  1. List local migrations in `backend/supabase/migrations/` directory
  2. Use Supabase MCP `list_migrations` with project_id `oepojxrximnmqwvnpoiu`
  3. Compare local vs remote migrations
  4. **All local migrations MUST exist in remote DB**
  5. If any migration is missing from remote: **STOP** and warn user to run `supabase db push` first


### Check 3: Compilation Check
- **Frontend (Next.js):**
  ```bash
  cd /Users/karthi/Documents/AI\ Projects/UnizyVoice && npm run build
  ```
  - Must exit with code 0
  - Check for TypeScript errors

- **Backend (Python):**
  ```bash
  cd /Users/karthi/Documents/AI\ Projects/UnizyVoice/backend && source venv/bin/activate && python -m py_compile main.py
  ```
  - Also run: `python -c "from routers import *; from services import *"` to verify imports
  - Must have no import errors

### Check 4: API Documentation Check
- If router files modified, check for corresponding documentation:
  - Look for `Docs/*.md` files related to the changed router
- Documentation should include:
  - API endpoint signature changes
  - Frontend files that consume the API
  - Webhook response changes (if applicable)
- If API changed but no docs updated: **FLAG** for user review

### Check 5: LLM Usage Tracking
- If any of these files are modified, check for LLM usage tracking:
  - `backend/services/gemini_service.py`
  - `backend/services/gemini_cache_service.py`
  - `backend/services/extraction_service.py`
  - Files with `google.generativeai` or `genai` imports
- Verify new Gemini calls have corresponding `llm_usage_service` logging:
  - `log_llm_usage()` or similar calls
  - `input_tokens`, `output_tokens`, `model` fields captured
- If new LLM call without usage tracking: **FLAG** for user review

## Approval Process

After running all checks, present a summary table:

```
## Pre-Commit Check Results

| Check | Status | Details |
|-------|--------|---------|
| Branch | [PASS/FAIL] | Current: [branch], Required: dev |
| Migrations | [PASS/SKIP/FAIL] | [X] local, [Y] remote, [Z] pending |
| API Auth | [PASS/FLAG] | [N] endpoints checked, [M] flagged |
| Frontend Build | [PASS/FAIL] | [build output summary] |
| Backend Compile | [PASS/FAIL] | [import check summary] |
| API Docs | [PASS/FLAG/SKIP] | [documentation status] |
| LLM Usage | [PASS/FLAG/SKIP] | [tracking status] |

### Flagged Items (if any)
- [List any items needing user attention]

### Changes to Commit
[Output of git status --short]

### Recommended Commit Message
[AI-generated commit message based on changes]
```

**Ask user for approval before proceeding.**

## Commit and Push

Only after user approval:

1. **Stage all changes:**
   ```bash
   git add -A
   ```

2. **Create commit with Co-Authored-By:**
   ```bash
   git commit -m "$(cat <<'EOF'
   [Commit message here]

   Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
   EOF
   )"
   ```

3. **Push to remote:**
   ```bash
   git push origin dev
   ```

4. **Verify push success:**
   ```bash
   git status
   ```

## Output Format

```
## Git Commit Summary

### Pre-Commit Checks
[Check results table]

### Commit Details
- **Branch:** dev
- **Commit Hash:** [hash]
- **Files Changed:** [count]
- **Insertions:** [+count]
- **Deletions:** [-count]

### Push Status
- **Remote:** origin/dev
- **Status:** [SUCCESS/FAILED]

### Next Steps (if any)
[Suggestions for follow-up actions]
```

## Commands Reference

```bash
# Check current branch
git branch --show-current

# Check staged files
git diff --cached --name-only

# Check for migration files
git diff --cached --name-only | grep -E "supabase/migrations/.*\.sql$"

# Check for router files
git diff --cached --name-only | grep -E "backend/routers/.*\.py$"

# Frontend build
npm run build

# Backend import check
cd backend && source venv/bin/activate && python -c "from routers import *; from services import *"

# Git status
git status --short

# Commit with HEREDOC
git commit -m "$(cat <<'EOF'
Message here

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"

# Push
git push origin dev
```

## Error Handling

- **Branch mismatch:** Offer to switch to dev or abort
- **Migration not applied:** Instruct user to run `supabase db push`
- **Build failure:** Show error output, do not proceed
- **Auth missing:** List endpoints needing auth, ask for confirmation
- **Push failure:** Show error, check for upstream changes
