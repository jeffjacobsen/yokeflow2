# Task Management SaaS - Project Specification

**Version:** 1.0
**Date:** December 2025
**Project Type:** Full-stack SaaS Application

## Overview

Build a modern task management SaaS application with real-time collaboration, team workspaces, and comprehensive project tracking capabilities.

## Core Features

### 1. User Authentication & Authorization
- Email/password authentication with JWT tokens
- Role-based access control (Admin, Manager, Member)
- OAuth integration (Google, GitHub)
- Session management and refresh tokens
- **Implementation details**: See `api-design.md#authentication`
- **Code example**: See `example-auth.py` for reference implementation pattern

### 2. Workspace Management
- Multi-tenant workspace architecture
- Workspace creation and invitation system
- Team member management
- Workspace settings and customization
- **Database schema**: See `database-schema.md#workspaces`

### 3. Project & Task Management
- Hierarchical structure: Workspaces → Projects → Tasks
- Task creation, assignment, and tracking
- Priority levels and due dates
- Status workflows (Todo, In Progress, Review, Done)
- Labels and custom fields
- **API endpoints**: See `api-design.md#projects-tasks`

### 4. Real-time Collaboration
- WebSocket-based live updates
- Real-time task updates across users
- Presence indicators (who's online)
- Activity feed
- **Technical implementation**: See `technical-architecture.md#websockets`

### 5. Comments & Attachments
- Task comments with mentions (@user)
- File attachments (images, documents)
- Comment threading
- **Storage architecture**: See `technical-architecture.md#file-storage`

## Technology Stack

### Frontend
- **Framework**: React 18 with TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **State Management**: Zustand
- **Real-time**: Socket.io client
- **Forms**: React Hook Form + Zod validation

### Backend
- **Runtime**: Node.js 20+
- **Framework**: Express.js with TypeScript
- **Database**: PostgreSQL 15+
- **ORM**: Prisma
- **Real-time**: Socket.io
- **Authentication**: JWT with bcrypt
- **File Storage**: Local filesystem (production: S3-compatible)

### Infrastructure
- **Deployment**: Docker containers
- **Environment**: Production & Development configurations
- **Database Migrations**: Prisma Migrate

## Project Structure

```
/
├── client/              # React frontend
│   ├── src/
│   │   ├── components/  # Reusable components
│   │   ├── pages/       # Page components
│   │   ├── hooks/       # Custom hooks
│   │   ├── lib/         # Utilities
│   │   └── types/       # TypeScript types
│   └── package.json
│
├── server/              # Express backend
│   ├── src/
│   │   ├── routes/      # API routes
│   │   ├── controllers/ # Request handlers
│   │   ├── services/    # Business logic
│   │   ├── middleware/  # Auth, validation, etc.
│   │   ├── models/      # Database models (Prisma)
│   │   └── socket/      # WebSocket handlers
│   └── package.json
│
├── prisma/              # Database schema & migrations
│   └── schema.prisma
│
├── docker-compose.yml   # Local development setup
└── README.md
```

## Detailed Specifications

For detailed information about specific aspects of the project, refer to these files:

- **API Design**: `api-design.md` - All REST endpoints and WebSocket events
- **Database Schema**: `database-schema.md` - Complete data model with relationships
- **Technical Architecture**: `technical-architecture.md` - System design, real-time features, file storage
- **UI/UX Guidelines**: `ui-design.md` - Component patterns, layouts, responsive design

## Development Workflow

### Stage 1: Foundation (Epics 1-5)
1. Project setup and infrastructure
2. Database schema and migrations
3. Authentication system
4. Basic API structure
5. Frontend foundation

### Stage 2: Core Features (Epics 6-12)
6. Workspace management
7. Project CRUD operations
8. Task management
9. Real-time updates
10. Comments system
11. File attachments
12. User interface components

### Stage 3: Enhancement (Epics 13-18)
13. Search and filtering
14. Activity feed
15. Notifications
16. User preferences
17. Workspace analytics
18. Polish and optimization

## Key Requirements

### Functional
- ✅ Users can create multiple workspaces
- ✅ Real-time collaboration across team members
- ✅ Comprehensive task management features
- ✅ Secure authentication and authorization
- ✅ File upload and storage
- ✅ Search and filtering capabilities

### Non-Functional
- ✅ Response time < 200ms for API calls
- ✅ Support for 100+ concurrent users per workspace
- ✅ Mobile-responsive design
- ✅ Cross-browser compatibility (Chrome, Firefox, Safari, Edge)
- ✅ Accessibility (WCAG 2.1 AA)
- ✅ Data encryption in transit (HTTPS)

## Success Criteria

1. All core features implemented and functional
2. Comprehensive test coverage (unit, integration, E2E)
3. Responsive design working on mobile/tablet/desktop
4. Real-time updates working reliably
5. Authentication and authorization secure
6. Clean, maintainable codebase with TypeScript
7. Complete API documentation
8. Docker deployment working

## Getting Started

After initialization, the agent will:
1. Create the complete project structure
2. Set up database with Prisma
3. Implement authentication system
4. Build core API endpoints
5. Create React frontend with Tailwind
6. Add WebSocket real-time features
7. Implement file upload system
8. Add comprehensive testing

---

**Note to Agent**: This is the main specification file. Refer to the other files in the `spec/` directory for detailed information about specific aspects of the system. Use lazy-loading - only read additional files when you need specific implementation details for the epic/task you're working on.
