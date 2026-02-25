# API Design Specification

Complete REST API and WebSocket event specifications for the Task Management SaaS.

## Base URL

```
Development: http://localhost:3010/api
Production: https://api.taskmanager.com/api
```

## Authentication

All authenticated endpoints require a JWT token in the `Authorization` header:
```
Authorization: Bearer <jwt_token>
```

### Auth Endpoints

#### POST /auth/register
Register a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securePassword123",
  "name": "John Doe"
}
```

**Response (201):**
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "name": "John Doe"
  },
  "accessToken": "jwt_token",
  "refreshToken": "refresh_token"
}
```

#### POST /auth/login
Authenticate existing user.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securePassword123"
}
```

**Response (200):**
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "name": "John Doe"
  },
  "accessToken": "jwt_token",
  "refreshToken": "refresh_token"
}
```

#### POST /auth/refresh
Refresh access token.

**Request:**
```json
{
  "refreshToken": "refresh_token"
}
```

**Response (200):**
```json
{
  "accessToken": "new_jwt_token"
}
```

#### POST /auth/logout
Invalidate refresh token.

**Request:**
```json
{
  "refreshToken": "refresh_token"
}
```

**Response (204):** No content

## Workspace Endpoints

#### GET /workspaces
List all workspaces for the authenticated user.

**Response (200):**
```json
{
  "workspaces": [
    {
      "id": "uuid",
      "name": "My Company",
      "slug": "my-company",
      "role": "admin",
      "memberCount": 12,
      "createdAt": "2025-01-01T00:00:00Z"
    }
  ]
}
```

#### POST /workspaces
Create a new workspace.

**Request:**
```json
{
  "name": "My Company",
  "slug": "my-company"
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "name": "My Company",
  "slug": "my-company",
  "role": "admin",
  "createdAt": "2025-01-01T00:00:00Z"
}
```

#### GET /workspaces/:workspaceId
Get workspace details.

**Response (200):**
```json
{
  "id": "uuid",
  "name": "My Company",
  "slug": "my-company",
  "description": "Our workspace",
  "members": [
    {
      "userId": "uuid",
      "name": "John Doe",
      "email": "john@example.com",
      "role": "admin",
      "joinedAt": "2025-01-01T00:00:00Z"
    }
  ],
  "projectCount": 5,
  "createdAt": "2025-01-01T00:00:00Z"
}
```

## Project Endpoints

#### GET /workspaces/:workspaceId/projects
List all projects in a workspace.

**Query Parameters:**
- `status` (optional): Filter by status (active, archived)
- `sort` (optional): Sort by field (name, createdAt, updatedAt)
- `order` (optional): Sort order (asc, desc)

**Response (200):**
```json
{
  "projects": [
    {
      "id": "uuid",
      "name": "Website Redesign",
      "description": "Redesign company website",
      "status": "active",
      "taskCount": 45,
      "completedTasks": 12,
      "createdAt": "2025-01-01T00:00:00Z"
    }
  ]
}
```

#### POST /workspaces/:workspaceId/projects
Create a new project.

**Request:**
```json
{
  "name": "Website Redesign",
  "description": "Redesign company website",
  "color": "#3B82F6"
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "name": "Website Redesign",
  "description": "Redesign company website",
  "color": "#3B82F6",
  "status": "active",
  "createdAt": "2025-01-01T00:00:00Z"
}
```

## Task Endpoints

#### GET /projects/:projectId/tasks
List all tasks in a project.

**Query Parameters:**
- `status` (optional): Filter by status
- `assignee` (optional): Filter by assignee user ID
- `priority` (optional): Filter by priority (low, medium, high, urgent)
- `search` (optional): Search query for title/description

**Response (200):**
```json
{
  "tasks": [
    {
      "id": "uuid",
      "title": "Design homepage mockup",
      "description": "Create Figma mockup for new homepage",
      "status": "in_progress",
      "priority": "high",
      "assignee": {
        "id": "uuid",
        "name": "Jane Smith"
      },
      "dueDate": "2025-01-15T00:00:00Z",
      "labels": ["design", "homepage"],
      "commentCount": 3,
      "attachmentCount": 2,
      "createdAt": "2025-01-01T00:00:00Z",
      "updatedAt": "2025-01-05T12:30:00Z"
    }
  ]
}
```

#### POST /projects/:projectId/tasks
Create a new task.

**Request:**
```json
{
  "title": "Design homepage mockup",
  "description": "Create Figma mockup for new homepage",
  "priority": "high",
  "assigneeId": "uuid",
  "dueDate": "2025-01-15T00:00:00Z",
  "labels": ["design", "homepage"]
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "title": "Design homepage mockup",
  "status": "todo",
  "priority": "high",
  "createdAt": "2025-01-01T00:00:00Z"
}
```

#### PATCH /tasks/:taskId
Update a task.

**Request:**
```json
{
  "title": "Updated title",
  "status": "in_progress",
  "priority": "urgent",
  "assigneeId": "uuid",
  "dueDate": "2025-01-20T00:00:00Z"
}
```

**Response (200):**
```json
{
  "id": "uuid",
  "title": "Updated title",
  "status": "in_progress",
  "updatedAt": "2025-01-05T12:30:00Z"
}
```

## Comment Endpoints

#### GET /tasks/:taskId/comments
Get all comments for a task.

**Response (200):**
```json
{
  "comments": [
    {
      "id": "uuid",
      "content": "Great progress! @john please review",
      "author": {
        "id": "uuid",
        "name": "Jane Smith"
      },
      "mentions": ["john"],
      "createdAt": "2025-01-05T10:00:00Z",
      "updatedAt": "2025-01-05T10:00:00Z"
    }
  ]
}
```

#### POST /tasks/:taskId/comments
Add a comment to a task.

**Request:**
```json
{
  "content": "Great progress! @john please review"
}
```

**Response (201):**
```json
{
  "id": "uuid",
  "content": "Great progress! @john please review",
  "author": {
    "id": "uuid",
    "name": "Current User"
  },
  "createdAt": "2025-01-05T10:00:00Z"
}
```

## WebSocket Events

### Connection
```javascript
// Connect with JWT token
const socket = io('http://localhost:3010', {
  auth: {
    token: 'jwt_token'
  }
});
```

### Join Workspace
Join a workspace room to receive real-time updates.

**Client → Server:**
```javascript
socket.emit('join:workspace', { workspaceId: 'uuid' });
```

### Task Events

#### Task Created
**Server → Client:**
```javascript
socket.on('task:created', (data) => {
  // data: { projectId, task: { ...taskData } }
});
```

#### Task Updated
**Server → Client:**
```javascript
socket.on('task:updated', (data) => {
  // data: { projectId, taskId, changes: { ...updatedFields } }
});
```

#### Task Deleted
**Server → Client:**
```javascript
socket.on('task:deleted', (data) => {
  // data: { projectId, taskId }
});
```

### Presence Events

#### User Online
**Server → Client:**
```javascript
socket.on('user:online', (data) => {
  // data: { userId, name }
});
```

#### User Offline
**Server → Client:**
```javascript
socket.on('user:offline', (data) => {
  // data: { userId }
});
```

## Error Responses

All endpoints return errors in this format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": {} // Optional additional context
  }
}
```

**Common Error Codes:**
- `UNAUTHORIZED` (401): Missing or invalid authentication
- `FORBIDDEN` (403): Insufficient permissions
- `NOT_FOUND` (404): Resource not found
- `VALIDATION_ERROR` (400): Invalid request data
- `CONFLICT` (409): Resource conflict (e.g., duplicate email)
- `SERVER_ERROR` (500): Internal server error

## Rate Limiting

- **Authenticated requests**: 1000 requests per hour
- **Unauthenticated requests**: 100 requests per hour

Rate limit headers:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1640995200
```

---

**Implementation Notes:**
- Use Express.js middleware for authentication (JWT)
- Implement rate limiting with `express-rate-limit`
- Use `socket.io` for WebSocket implementation
- Validate all request bodies with Zod schemas
- Return appropriate HTTP status codes
