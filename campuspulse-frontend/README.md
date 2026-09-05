# CampusPulse + MannMitra — Frontend

A modular, responsive React + Vite frontend for a privacy-first student wellbeing platform. The UI supports three separate experiences: **Student**, **Counselor**, and **Admin**.

> **Frontend only:** this repository contains UI, client-side routing, demo state, and a clean service/API layer. Production authentication, database storage, RAG/LLM inference, risk classification, counselor workflows, and institutional analytics belong to the backend.

## Tech Stack

### Framework & Build Tool
- React 18
- Vite
### Languages
- JavaScript (ES6+)
- JSX
- CSS
### Libraries
- React Router DOM
- Axios
- Lucide React


## Run Locally

```bash
npm install
npm run dev
```

Development server:

```text
http://localhost:5317
```

Production preview:

```bash
npm run build
npm run preview
```



## Role-Based Routing

The frontend has three separate portals.

### Student

- Student Dashboard
- MannMitra
- Daily Check-in
- Wellness Zone
- My Insights
- Connect with a Counselor
- Immediate support: Tele-MANAS and 112

### Counselor

- Command Overview
- Priority Cases
- Interventions
- Follow-ups Due
- Campus Analytics

### Admin

- Campus Overview
- Department Trends
- Stress Forecasting
- Data Governance

The counselor and admin areas are intentionally separate from the student experience and can be connected to different backend permissions later.

## Backend Integration Guide

The frontend is intentionally organized so the backend team does **not** need to search through page components to find API calls.

All network integration starts in:

```text
src/services/api.js
```

The current API boundary is:

| Purpose | Frontend service | Current route placeholder |
|---|---|---|
| Backend health | `api.js` | `/health` |
| MannMitra text chat | `mannmitra.js` | `/api/mannmitra/chat` |
| MannMitra voice | `mannmitra.js` | `/api/mannmitra/voice` |
| Daily check-in | `wellbeing.js` | `/api/wellbeing/check-in` |
| Student insights | `wellbeing.js` | `/api/wellbeing/insights` |
| Counselor messages | `wellbeing.js` | `/api/counselor/messages` |

These are **frontend integration placeholders**, not claims that the backend already exposes exactly these routes. The backend team can change only `apiConfig` and/or the small service functions rather than rewriting the UI.

### Environment variable

Create `.env` from `.env.example`:

```env
VITE_API_BASE_URL=http://localhost:8000
```

For a deployed backend:

```env
VITE_API_BASE_URL=https://your-backend-domain.example
```

Restart Vite after changing `.env`.

## MannMitra Backend Contract

The frontend is prepared for the existing MannMitra backend architecture: text interaction, risk/triage processing, RAG-assisted responses, and voice analysis.

A recommended text response shape is:

```json
{
  "message": "Supportive response from MannMitra",
  "risk_level": "Green",
  "session_id": "optional-session-id",
  "sources": []
}
```

Recommended `risk_level` values:

```text
Green
Yellow
Red
```

If the backend already uses different field names, map them inside `src/services/mannmitra.js` or the MannMitra page instead of spreading backend-specific logic across components.

For voice:

```text
Frontend microphone/audio file
        ↓
mannmitra.sendVoiceMessage()
        ↓
Backend speech-to-text / speech analysis
        ↓
Risk + emotion interpretation / RAG response
        ↓
JSON response
        ↓
MannMitra UI
```

## Daily Check-In Contract

The check-in page should send structured wellbeing inputs to:

```text
POST /api/wellbeing/check-in
```

Example payload:

```json
{
  "mood": 3,
  "stress": 4,
  "sleep": 3,
  "note": "optional user text"
}
```

The backend can validate, store, classify, and aggregate this data. The frontend should not independently decide a clinical diagnosis.

## Counselor Communication

The Student portal provides counselor cards with contact details and a contact action.

For production:

```text
Student
  ↓
POST /api/counselor/messages
  ↓
Backend authentication + authorization
  ↓
Database / message service
  ↓
Counselor portal
```

The current frontend contains demo/mock behavior so the UI can be demonstrated before backend integration. Replace that demo persistence with the backend service when the API is ready.

The backend should enforce counselor/student authorization server-side. Never rely on frontend role checks as the security boundary.

## Authentication Integration

`src/services/auth.js` currently provides local demo user state so the three portals can be tested without a backend.

For production, replace the demo functions with your authentication flow, for example:

```text
Login UI
  ↓
POST /auth/login
  ↓
Backend verifies credentials
  ↓
Access token / secure session
  ↓
Frontend stores only what is appropriate
  ↓
Role-based routing
```

Recommended production behavior:

- Backend is the source of truth for identity and role.
- Protect counselor/admin API endpoints server-side.
- Prefer secure, short-lived authentication/session mechanisms.
- Do not put secrets, API keys, Gemini keys, RAG credentials, or database credentials in the frontend.

## DPDP / Privacy Design

The UI follows a **DPDP Act-aligned privacy-by-design direction**, including privacy notices, minimization language, anonymized/aggregated admin views, and human-review messaging.

This frontend alone does **not** establish legal compliance. Production compliance requires the backend, institutional policies, consent/notice flows, retention controls, access controls, security measures, grievance processes, and other applicable requirements to be implemented and reviewed appropriately.

For admin analytics, the intended design is:

```text
Individual student data
        ↓
Authorized backend processing
        ↓
Aggregation / anonymization
        ↓
Institutional trends
        ↓
Admin dashboard
```

Avoid exposing individual student wellbeing records to administrators unless the backend authorization and institutional policy explicitly allow it.

## Emergency Support

The student UI provides quick access to:

- **Tele-MANAS: 14416** — mental-health support
- **112** — India's emergency response number

These should remain clearly separated from ordinary counselor communication in the UI.

## Wellness Activities

The Wellness Zone includes modular activities such as:

- Box Breathing
- Focus Sprint
- Mind Match
- Color Calm
- Mood Garden
- Mini Meditation

These are frontend wellbeing activities and should not be presented as medical treatment or diagnosis.

## What the Backend Team Should Change

The backend team should primarily need to work around these boundaries:

1. Set `VITE_API_BASE_URL`.
2. Confirm/adjust endpoint paths in `src/services/api.js`.
3. Match request/response payloads in `mannmitra.js` and `wellbeing.js`.
4. Connect real authentication in `auth.js`.
5. Add authorization on every protected backend route.
6. Connect real counselor messaging/storage.
7. Replace demo dashboard data with authorized API responses.
8. Add loading/error/empty states where API calls are introduced.
9. Keep all model/RAG/API secrets on the backend.

**Do not put backend/RAG/Gemini keys inside React environment variables intended for browser use.** Anything exposed through a Vite `VITE_*` variable can be visible to users.

## Git Workflow

Recommended branch structure:

```text
main
 ├── frontend
 ├── backend
 └── integration
```

Or use feature branches:

```text
feature/student-dashboard
feature/mannmitra-api
feature/counselor-portal
feature/admin-analytics
```

Keep frontend and backend changes in separate commits where possible. This makes integration and debugging easier.

## Important Notes

- Dark-only UI; there is no light-mode switch.
- The project uses React/JSX for UI components. `index.html` is only the Vite application entry document required by the build tool.
- Demo values shown in dashboards must be replaced with backend data before production.
- Frontend role routing is for UX; backend authorization is the actual security boundary.
- No sensitive backend credentials should ever be committed to GitHub.
