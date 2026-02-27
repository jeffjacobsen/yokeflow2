# AI-Powered Specification Generation

## Overview

YokeFlow 2 includes AI-powered specification generation that allows users to describe their application in natural language and have Claude generate a complete, structured technical specification. This feature dramatically simplifies the project initialization process.

**Status**: ✅ Complete (January 20, 2026)
**Created by**: https://github.com/imagicrafter

## Features

### Natural Language Input
- Users describe their application idea in plain English
- No technical specification writing expertise required
- Support for context files (mockups, requirements docs, etc.)

### Real-time Generation
- Server-Sent Events (SSE) for streaming progress
- Live preview as specification is generated
- Visual progress indicators with helpful messages

### Intelligent Validation
- Automatic validation after generation
- Checks for required sections and completeness
- Provides errors, warnings, and improvement suggestions

### Editable Output
- Full markdown editor with syntax highlighting
- Preview mode for formatted viewing
- Export and copy functionality
- Manual validation on demand

## Architecture

### Backend Components

#### Spec Generator (`server/generation/spec_generator.py`)
- Uses Claude Agent SDK for consistency with main agent
- Generates comprehensive specifications using claude-sonnet-4-6
- Streams responses via SSE for real-time updates
- Handles context files and natural language descriptions

#### Spec Validator (`server/generation/spec_validator.py`)
- Validates markdown specifications for required sections
- Checks technical completeness and clarity
- Provides actionable improvement suggestions
- Supports multiple project types (web, API, CLI, data)

#### API Endpoints (`server/api/app.py`)
- `POST /api/generate-spec` - Generate specification with SSE streaming
- `POST /api/validate-spec` - Validate specification content

### Frontend Components

#### Create Project Page (`web-ui/src/app/create/page.tsx`)
- Mode toggle between "Upload Spec" and "Generate with AI"
- Natural language description input
- Context file upload support
- Real-time generation progress
- Validation feedback display

#### Spec Editor Component (`web-ui/src/components/SpecEditor.tsx`)
- Markdown editing with syntax highlighting
- Toggle between edit and preview modes
- Debounced validation (1 second delay)
- Word and line count statistics
- Copy to clipboard and download functionality

## User Workflow

1. **Choose Generation Mode**
   - Navigate to Create Project page
   - Select "Generate with AI" mode

2. **Describe Application**
   - Enter natural language description
   - Optionally upload context files (mockups, requirements)
   - Click "Generate Specification"

3. **Monitor Generation**
   - Watch real-time progress updates
   - "This may take a few minutes" message sets expectations
   - Specification streams in progressively

4. **Review and Edit**
   - Automatic validation runs on completion
   - View validation feedback (errors, warnings, suggestions)
   - Edit specification if needed
   - Toggle between edit and preview modes

5. **Create Project**
   - Once satisfied, proceed with project creation
   - Specification becomes the project blueprint

## API Reference

### Generate Specification

**Endpoint**: `POST /api/generate-spec`
**Content-Type**: `application/json`
**Accept**: `text/event-stream`

**Request Body**:
```json
{
  "description": "Natural language description of the application",
  "context_files": {
    "filename.txt": "base64_encoded_content"
  },
  "project_name": "my-project"
}
```

**Response**: Server-Sent Events stream
```
data: {"event": "start", "message": "Starting specification generation..."}
data: {"event": "progress", "content": "# Application Specification\n\n## Overview..."}
data: {"event": "complete", "message": "Specification generated successfully"}
```

### Validate Specification

**Endpoint**: `POST /api/validate-spec`
**Content-Type**: `application/json`

**Request Body**:
```json
{
  "spec_content": "Markdown specification content",
  "project_type": "web|api|cli|data|general"
}
```

**Response**:
```json
{
  "valid": true,
  "errors": [],
  "warnings": ["Consider adding error handling section"],
  "sections_found": ["Overview", "Tech Stack", "API"],
  "sections_missing": ["Testing Strategy"],
  "suggestions": ["Add deployment configuration details"]
}
```

## Configuration

### Model Selection
The spec generator uses the same model as the coding agent (claude-sonnet-4-6) by default. This can be configured in `.yokeflow.yaml`:

```yaml
models:
  coding: claude-sonnet-4-6  # Used for spec generation
```

### Authentication
Uses the same OAuth token as the main YokeFlow agent:
- Reads from environment variable `CLAUDE_CODE_OAUTH_TOKEN`
- Falls back to `.env` file if needed

## Technical Implementation Details

### SSE Streaming
- Chunks specification into manageable pieces
- Accumulates content on frontend for complete spec
- Handles connection interruptions gracefully

### Validation Logic
Required sections vary by project type:
- **Web Projects**: Frontend, Backend, Database sections
- **API Projects**: Endpoints, Authentication, Data Models
- **CLI Projects**: Commands, Arguments, Configuration
- **Data Projects**: Pipeline, Processing, Storage

### Error Handling
- Graceful fallback for connection issues
- Clear error messages for user
- Automatic retry logic for transient failures

## Troubleshooting

### "Specification content is required" Error
- Ensure frontend sends `spec_content` field
- Check that specification is not empty

### Model Not Found Error
- Verify correct model name: `claude-sonnet-4-6`
- Check OAuth token is valid and present

### Validation Always Shows "Needs Improvement"
- Check that API response maps correctly to frontend
- Ensure `valid` → `isValid` transformation

### Generation Takes Too Long
- Normal generation time: 1-3 minutes
- Check API server logs for errors
- Verify OAuth token hasn't expired

## Future Enhancements

Potential improvements for future versions:

1. **Template Library**
   - Pre-built specification templates
   - Industry-specific starting points
   - Common architecture patterns

2. **Interactive Refinement**
   - Chat-based specification improvement
   - Clarifying questions from AI
   - Iterative enhancement workflow

3. **Visual Specification Builder**
   - Drag-and-drop component selection
   - Visual architecture diagrams
   - Auto-generated specifications from diagrams

4. **Specification Versioning**
   - Track specification changes over time
   - Compare different versions
   - Rollback capabilities

5. **Team Collaboration**
   - Shared specification editing
   - Comments and suggestions
   - Approval workflows

## Related Documentation

- [API Documentation](./api-usage.md) - Complete API reference
- [Configuration](./configuration.md) - YokeFlow configuration options