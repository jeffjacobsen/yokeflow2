# Contributing to YokeFlow

Thank you for your interest in contributing to YokeFlow! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)
- [Community](#community)

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/yokeflow.git
   cd yokeflow
   ```
3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/ms4inc/yokeflow.git
   ```
4. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Setup

Follow the setup instructions in [README.md](README.md) to get YokeFlow running locally:

### Prerequisites
- Node.js 20+ (for web UI and MCP server)
- Python 3.9+ (for core platform)
- Docker (for PostgreSQL and sandboxing)
- Claude API token

### Quick Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install web UI dependencies
cd web-ui
npm install
cd ..

# Build MCP task manager
cd mcp-task-manager
npm install
npm run build
cd ..

# Start PostgreSQL
docker-compose up -d

# Initialize database
python scripts/init_database.py --docker

# Configure environment
cp .env.example .env
# Edit .env with your Claude API token
```

## Project Background

YokeFlow evolved from [Anthropic's Autonomous Coding demo](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding), transforming it into an API-first platform with comprehensive features including:
- TypeScript/React Web UI with real-time monitoring
- REST API with 17+ endpoints
- PostgreSQL database with async operations
- Docker sandbox support for secure execution
- Automated verification system with test generation
- Production hardening (retry logic, checkpointing, intervention)

While we've made significant improvements, there are still exciting opportunities to enhance the platform further.

## Areas for Contribution

### 1. Core Enhancements

**High-Impact Areas:**
- **Brownfield Support** - Extend YokeFlow to modify existing codebases (not just greenfield)
- **Non-UI Applications** - Support for CLIs, APIs, libraries, and backend services
- **Selective Browser Testing** - Limit browser verification to UI-related tasks only
- **Authentication System** - Implement the planned per-user authentication (see TODO-FUTURE.md)

### 2. Integration & Connectivity

**Expand YokeFlow's ecosystem:**
- **GitHub Integration** - Automatic repository creation, PR management, issue tracking
- **Task Manager Integration** - Connect with Jira, Linear, GitHub Projects, etc.
- **Spec Writer Companion** - AI-powered specification writing tool
- **CI/CD Integration** - GitHub Actions, GitLab CI, Jenkins workflows

### 3. User Interface Improvements

The current UI prioritizes functionality over polish. See [UI-NOTES.md](UI-NOTES.md) for details:
- Enhanced visual design and UX
- Better progress visualization
- Real-time session monitoring improvements
- Mobile responsiveness
- Dark mode support

### 4. Intelligent Agent Behavior

**Make the agent smarter:**
- **Dynamic Model Selection** - Choose coding models based on task complexity
- **Context-Aware Testing** - Smarter test generation based on task type
- **Adaptive Verification** - Skip browser tests for non-UI features
- **Cost Optimization** - Use cheaper models for simple tasks

### 5. Project Management Features

**Enhance project control:**
- **Epic/Task/Test Editing** - Allow manual editing before coding sessions begin
- **Final Project Review** - Comprehensive comparison between created app and specs
- **Mid-Project Adjustments** - Support for spec changes during development
- **Task Dependencies** - Better handling of task ordering and dependencies

### 6. Prompt Engineering

**For less technical contributors:**
- Experiment with initialization prompts for better task generation
- Optimize coding prompts for specific project types (e-commerce, SaaS, dashboards)
- Test various project specifications to identify best practices
- Document what types of specs work best with YokeFlow
- Improve error recovery prompts

### 7. Platform Compatibility

**Broaden platform support:**
- Windows environment testing and adjustments
- Linux distribution testing
- E2B sandbox integration (alternative to Docker)
- Cloud deployment configurations (AWS, GCP, Azure)

### 8. Performance & Scalability

**Make YokeFlow faster and more efficient:**
- Database query optimization
- Parallel task execution
- Caching strategies
- Memory usage optimization
- Session resumption improvements

## Current Limitations & Known Issues

Understanding current limitations helps identify contribution opportunities:

### Core Limitations
1. **Greenfield Projects Only** - Currently limited to creating new projects from scratch
2. **Web Application Focus** - Primarily designed for UI-based web applications
3. **Universal Browser Verification** - Verifies every feature with browser automation

### Platform Compatibility
- Developed and tested primarily on macOS
- May require adjustments for Windows environments
- Docker support helps with cross-platform consistency

### Known Gaps (see YOKEFLOW_REFACTORING_PLAN.md)
- Authentication not yet implemented (2 tests deferred)
- Some integration tests require database setup
- Documentation could always be improved

## How to Contribute

### Reporting Bugs

Before creating a bug report, please:
1. **Search existing issues** to avoid duplicates
2. **Check the troubleshooting section** in README.md
3. **Test with the latest version** from the main branch

When creating a bug report, include:
- **Clear title** describing the issue
- **Steps to reproduce** the bug
- **Expected behavior** vs. actual behavior
- **Environment details** (OS, Python/Node versions, Docker version)
- **Logs** from `projects/[project]/yokeflow/logs/` if applicable
- **Screenshots** if relevant

Use the bug report template when creating issues.

### Suggesting Enhancements

Enhancement suggestions are welcome! Please:
1. **Check [TODO-FUTURE.md](TODO-FUTURE.md)** to see if it's already planned
2. **Create an issue** using the feature request template
3. **Describe the use case** and why it's valuable
4. **Provide examples** if applicable

### Contributing Code

We welcome contributions in these areas:

**High Priority:**
- Bug fixes
- Documentation improvements
- Test coverage expansion
- Performance optimizations

**Medium Priority:**
- New features (discuss in an issue first)
- UI/UX improvements
- Integration with new services

**Lower Priority:**
- Refactoring (unless it improves performance/maintainability significantly)
- Cosmetic changes

## Pull Request Process

### Before Submitting

1. **Update from upstream**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run tests**:
   ```bash
   # Security tests
   python tests/test_security.py

   # Database tests
   python tests/test_database_abstraction.py

   # MCP tests
   python tests/test_mcp.py
   ```

3. **Check code style**:
   ```bash
   # Python: Follow PEP 8
   # TypeScript: Use project's ESLint config
   cd web-ui && npm run lint
   ```

4. **Update documentation** if you've changed:
   - API endpoints (update api/README.md)
   - Configuration options (update docs/configuration.md)
   - User-facing features (update README.md, CLAUDE.md)
   - Database schema (update schema/postgresql/)

### Submitting the PR

1. **Push your branch**:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create Pull Request** on GitHub

3. **Fill out the PR template** completely:
   - Clear description of changes
   - Link to related issues
   - Screenshots/demos if applicable
   - Testing performed
   - Documentation updates

4. **Respond to review feedback** promptly

### PR Requirements

- ✅ All tests pass
- ✅ No merge conflicts
- ✅ Documentation updated
- ✅ Follows coding standards
- ✅ Commit messages are clear
- ✅ PR description is complete

## Coding Standards

### Python

- **Follow PEP 8** style guide
- **Use type hints** for function signatures
- **Write docstrings** for modules, classes, and functions
- **Keep functions focused** (single responsibility)
- **Use async/await** for database operations

Example:
```python
async def get_project_status(project_id: str) -> Dict[str, Any]:
    """
    Get the current status of a project.

    Args:
        project_id: UUID of the project

    Returns:
        Dictionary containing project status information

    Raises:
        ValueError: If project_id is invalid
        DatabaseError: If database query fails
    """
    # Implementation
```

### TypeScript/React

- **Use TypeScript** for all new code
- **Follow React best practices** (hooks, functional components)
- **Use proper types** (avoid `any`)
- **Components should be focused** and reusable
- **Use Tailwind CSS** for styling

Example:
```typescript
interface ProjectStatusProps {
  projectId: string;
  onUpdate?: (status: ProjectStatus) => void;
}

export function ProjectStatus({ projectId, onUpdate }: ProjectStatusProps) {
  // Implementation
}
```

### Commit Messages

Follow conventional commits format:

```
type(scope): brief description

Detailed explanation of what changed and why.

Fixes #123
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(api): add endpoint for project duplication

Add POST /api/projects/{id}/duplicate endpoint that creates
a copy of an existing project with a new name.

Fixes #456

---

fix(web-ui): prevent session logs infinite scroll bug

The logs viewer was continuously fetching when scrolled to
bottom. Added debouncing to prevent excessive API calls.

Fixes #789
```

## Testing Guidelines

### Manual Testing

Before submitting, test these scenarios:

1. **Create a new project** via Web UI
2. **Run initialization session** (Session 0)
3. **Run a coding session** (Session 1+)
4. **Verify real-time updates** work in Web UI
5. **Check session logs** are readable
6. **Test error handling** (stop/restart sessions)

### Automated Testing

Add tests for:
- **New API endpoints** (integration tests)
- **Database operations** (unit tests)
- **Security validations** (security tests)
- **UI components** (component tests - future)

See [tests/README.md](tests/README.md) for testing details.

## Documentation

### User Documentation

Update these files when changing user-facing features:
- **README.md** - Main user guide with v2.0 features
- **CLAUDE.md** - Quick reference for AI agents
- **QUICKSTART.md** - 5-minute getting started guide
- **CHANGELOG.md** - Document all changes
- **docs/** - Detailed documentation

### Developer Documentation

Update these files when changing architecture/APIs:
- **docs/developer-guide.md** - Technical architecture
- **docs/api-usage.md** - Complete API endpoint reference (17+ endpoints)
- **docs/verification-system.md** - Automated testing framework
- **docs/input-validation.md** - Validation framework guide
- **docs/mcp-usage.md** - MCP integration details
- **Code comments** - Inline documentation

### Additional Resources

- **[TODO-FUTURE.md](TODO-FUTURE.md)** - Detailed suggestions for future enhancements
- **[YOKEFLOW_REFACTORING_PLAN.md](YOKEFLOW_REFACTORING_PLAN.md)** - Remaining P1/P2 work items
- **[UI-NOTES.md](UI-NOTES.md)** - Specific UI improvement opportunities
- **[docs/testing-guide.md](docs/testing-guide.md)** - Comprehensive testing guide

### Writing Style

- **Be concise** but complete
- **Use examples** to illustrate concepts
- **Include code snippets** where helpful
- **Link to related docs** for context
- **Keep formatting consistent** with existing docs

## Community

### Getting Help

- **GitHub Discussions** - Ask questions, share ideas
- **GitHub Issues** - Report bugs, request features
- **Documentation** - Check docs/ directory first

### Communication

- **Be respectful** and constructive
- **Assume good intentions** from others
- **Stay on topic** in discussions
- **Help others** when you can
- **Give credit** where it's due

### Recognition

Contributors will be:
- Listed in release notes
- Acknowledged in documentation
- Invited to collaborate on future features

## Experimentation & Forking

We encourage community members to fork YokeFlow and experiment with bold ideas!

### Why Fork?

- **Rapid Prototyping** - Test ideas without waiting for PR review
- **Experimental Features** - Try features that may not fit the main project
- **Learning** - Understand the codebase by modifying it
- **Innovation** - Discover new approaches to autonomous coding

### Ideas for Forks

1. **Specialized Agents**
   - Create agents optimized for specific frameworks (React, Django, FastAPI)
   - Build domain-specific agents (e-commerce, SaaS, data science)
   - Experiment with different Claude models and configurations

2. **Alternative Architectures**
   - Try different database systems (MongoDB, SQLite)
   - Implement alternative sandboxing (E2B, Firecracker)
   - Experiment with different UI frameworks

3. **Novel Features**
   - Multi-agent collaboration
   - Voice-based specification input
   - Real-time code collaboration
   - AI-powered code review

### Sharing Your Fork

If your fork proves successful:
1. **Document your approach** in your fork's README
2. **Share in GitHub Discussions** to inspire others
3. **Consider upstreaming** if it fits YokeFlow's goals
4. **Write blog posts** about your learnings

### Guidelines for Experimentation

- **Experiment Freely** - Don't be afraid to break things in your fork
- **Document Findings** - Share what works and what doesn't
- **Credit Original** - Acknowledge YokeFlow in your fork
- **Share Knowledge** - Help the community learn from your experiments
- **Test Thoroughly** - Ensure your changes work before sharing

---

**Questions?** Open a discussion on GitHub or create an issue.

**Ready to contribute or experiment? We're excited to see what you build!** 🚀

---

*Remember: YokeFlow is about pushing the boundaries of autonomous development. Your contributions and experiments help shape the future of AI-assisted coding.*
