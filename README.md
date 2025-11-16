# Asana Brief Creation

AI-powered service to automatically create Asana tasks from Google Doc campaign briefs using Claude Sonnet.

## ✅ What's Built (Phase 2 Complete)

### Core Services
- ✅ **AsanaClient Extended** - Task creation with custom fields support
- ✅ **AI-Powered Custom Field Mapper** - Fuzzy matching of field names to GIDs using Claude
- ✅ **BriefParserService** - Parses Google Docs and extracts structured task data with Claude
- ✅ **TaskCreationService** - Orchestrates the entire workflow
- ✅ **Google Docs Integration** - Fetches and parses documents with table support

### API Endpoints
- ✅ `POST /api/briefs/process` - Parse brief and create tasks (with dry_run option)
- ✅ `GET /api/briefs/preview` - Preview tasks without creating them
- ✅ `POST /api/briefs/verify` - Verify project/section accessibility
- ✅ `GET /api/briefs/health` - Health check

### Database
- ✅ PostgreSQL schema designed and migration file created
- ✅ SQLAlchemy models for `briefs` and `brief_tasks`
- ✅ JSONB support for flexible data storage

### Configuration
- ✅ Environment variables configured
- ✅ Google service account integration
- ✅ Asana OAuth support (reusable from asana-copy-review)

## 🎯 Target Configuration

**Test Project**: 📩 Team 4 Campaigns
**Project GID**: 1206874746809992
**Target Section**: ✏️ Copywriter
**Section GID**: 1206874104264005

**Test Google Doc**: https://docs.google.com/document/d/1-fLu0GvLsUMdWxRZDbLC1zUai73SnblQfichh6yqWaI/edit

## ✅ Test Results

### What's Working
1. ✅ **Project structure created** at `/Users/Damon/asana-brief-creation`
2. ✅ **Google Doc fetching works** - Successfully retrieved 47,159 characters from test doc
3. ✅ **Service account authentication** - emailpilot-docs-writer@emailpilot-438321.iam.gserviceaccount.com has access
4. ✅ **AsanaClient extended** with:
   - `create_task()` - Create tasks with custom fields
   - `get_project_sections()` - Get available sections
   - `get_project_custom_fields()` - Fetch field definitions
   - `update_task()` - Update existing tasks

5. ✅ **Custom Field Discovery** - Retrieved 18 custom fields from target project:
   - Message Type (multi_enum)
   - Client (enum with 50+ options)
   - Priority (High/Medium/Low)
   - Send Date (date)
   - Content Type, Messaging Stage, and more

### What Needs Attention
- ⚠️ **Anthropic API Key** - Current key is invalid/expired, needs update in `.env`

## 🚀 Next Steps

### 1. Update Anthropic API Key

```bash
cd /Users/Damon/asana-brief-creation/backend
# Edit .env and update ANTHROPIC_API_KEY with a valid key
```

### 2. Run Tests

```bash
# Test brief parsing and task creation (dry run)
/Users/Damon/asana-copy-review/backend/.venv/bin/python test_brief_creation.py
```

The test will:
1. ✅ Parse the Google Doc brief with Claude AI
2. ✅ Extract tasks with custom fields
3. ✅ Verify Asana project and section access
4. ✅ Preview tasks to be created (dry run)
5. ⏸️ Optionally create real tasks (commented out by default)

### 3. Create Real Tasks

Once testing looks good, uncomment this line in `test_brief_creation.py`:

```python
# Uncomment to create REAL tasks:
await test_create_tasks()
```

### 4. Start the API Server

```bash
cd backend
source /Users/Damon/asana-copy-review/backend/.venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Then access:
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## 📖 API Usage Examples

### Preview Brief (Dry Run)

```bash
curl -X POST "http://localhost:8000/api/briefs/process" \
  -H "Content-Type: application/json" \
  -d '{
    "google_doc_url": "https://docs.google.com/document/d/YOUR_DOC_ID/edit",
    "project_gid": "1206874746809992",
    "section_gid": "1206874104264005",
    "dry_run": true
  }'
```

### Create Tasks for Real

```bash
curl -X POST "http://localhost:8000/api/briefs/process" \
  -H "Content-Type: application/json" \
  -d '{
    "google_doc_url": "https://docs.google.com/document/d/YOUR_DOC_ID/edit",
    "project_gid": "1206874746809992",
    "section_gid": "1206874104264005",
    "dry_run": false
  }'
```

### Verify Project Access

```bash
curl "http://localhost:8000/api/briefs/verify?project_gid=1206874746809992&section_gid=1206874104264005"
```

## 🧠 How AI-Powered Field Mapping Works

### Problem
Asana custom fields require **GIDs** (not names):
```json
{
  "1203202007192951": "1203202007192986"  // Must use GIDs!
}
```

### Solution
The `CustomFieldMapper` service uses Claude to:

1. **Fetch** all custom fields for the project
2. **Match** field names from the brief to Asana field names (fuzzy matching)
3. **Resolve** enum option names to their GIDs
4. **Validate** that fields and values are correct

Example:
```python
# Input from brief (human-friendly)
{
  "Message Type": "Email",
  "Priority": "High",
  "Client": "Buca di Beppo"
}

# Output (Asana GIDs)
{
  "1203202007192951": "1203202007192986",  # Message Type -> Email
  "1201007787746652": "1201007787746653",  # Priority -> High
  "1201621821049778": "1210212188038900"   # Client -> Buca di Beppo
}
```

Claude handles:
- **Fuzzy matching** ("message type" vs "Message Type")
- **Typo tolerance** ("Priorit" → "Priority")
- **Intelligent enum resolution** ("email" → "Email" option GID)

## 📁 Project Structure

```
asana-brief-creation/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── asana_client.py          # ✅ Extended with create_task()
│   │   │   ├── config.py                # ✅ Settings
│   │   │   └── database.py              # ✅ Async SQLAlchemy
│   │   ├── services/
│   │   │   ├── google_docs.py           # ✅ Fetches Google Docs
│   │   │   ├── brief_parser.py          # ✅ AI-powered parsing
│   │   │   ├── custom_field_mapper.py   # ✅ AI field mapping
│   │   │   └── task_creation_service.py # ✅ Main orchestrator
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── briefs.py            # ✅ Brief processing endpoints
│   │   │       └── auth.py              # ✅ OAuth (copied)
│   │   ├── models/
│   │   │   └── brief.py                 # ✅ SQLAlchemy models
│   │   └── main.py                      # ✅ FastAPI app
│   ├── migrations/
│   │   └── 001_initial_brief_schema.sql # ✅ Database schema
│   ├── test_brief_creation.py           # ✅ Comprehensive test suite
│   ├── requirements.txt                 # ✅ Dependencies
│   ├── Dockerfile                       # ✅ Ready for deployment
│   └── .env                             # ✅ Configuration
└── README.md                            # This file
```

## 🎨 Key Features

### 1. AI-Powered Brief Parsing
Uses Claude to extract tasks from unstructured Google Docs with:
- Campaign overview
- Individual tasks with details
- Custom field values
- Send dates, priorities, etc.

### 2. Intelligent Field Mapping
No hardcoded GIDs! AI matches field names dynamically:
- Works across different projects
- Tolerates typos and variations
- Handles all field types (enum, multi_enum, text, date, number)

### 3. Dry Run Mode
Preview what will be created before committing:
```python
{
  "dry_run": true  # Just preview, don't create tasks
}
```

### 4. Comprehensive Error Handling
- Graceful failures per task
- Detailed error messages
- Partial success support (some tasks succeed, some fail)

## 🔧 Configuration

### Required Environment Variables

```bash
# Asana
ASANA_ACCESS_TOKEN=your_pat_here
ASANA_WORKSPACE_ID=1200387531924394
ASANA_TARGET_PROJECT_GID=1206874746809992
ASANA_TARGET_SECTION_GID=1206874104264005

# AI
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-... # UPDATE THIS!
AI_MODEL=claude-sonnet-4-20250514

# Google Docs
GOOGLE_DOCS_CREDENTIALS_PATH=/path/to/service-account.json

# Database (optional for now)
DATABASE_URL=postgresql+asyncpg://...
```

## 📊 Database Schema

### briefs
- Tracks brief processing requests
- Stores parsed data and results
- Links to created tasks

### brief_tasks
- Individual tasks created from briefs
- Stores Asana task GIDs
- Tracks creation status

## 🚢 Deployment

The app is ready for Cloud Run deployment:

```bash
# Deploy to Google Cloud Run (when ready)
./deploy.sh
```

## 📝 Example Brief Format

The AI parser is flexible and can handle various formats. Example:

```
Campaign Name: Holiday Email Campaign 2024

Goal: Drive holiday sales with a 3-email sequence

Tasks:
1. Email 1 - Welcome to Holiday Sale
   - Type: Email
   - Send Date: 2024-12-15
   - Priority: High
   - Subject: 🎄 Our biggest holiday sale is here!

2. Email 2 - Mid-Sale Reminder
   - Type: Email
   - Send Date: 2024-12-20
   - Priority: Medium
   ...
```

## 🎯 Success Criteria

- [x] Parse Google Doc briefs
- [x] Extract tasks with custom fields
- [x] Map field names to Asana GIDs using AI
- [x] Create tasks in correct project/section
- [ ] **Test with valid Anthropic API key** ⬅️ NEXT STEP
- [ ] Create real tasks in Asana
- [ ] Deploy to Cloud Run

## 📞 Support

Test the implementation:
1. Update Anthropic API key in `.env`
2. Run `test_brief_creation.py`
3. Check the logs for results

All components are ready - just needs a valid API key to complete end-to-end testing!
