# Development Checkpoint
Date: 2026-05-19

## Git
Repo initialized. Commit `c1d4e92` — full codebase.

## Completed Features

### Backend
| File | Change |
|------|--------|
| `backend/app/main.py` | Guardrail startup cache (`app.state.guardrails`) |
| `backend/app/api/routes/guardrails.py` | Cache reload on create/update/toggle/delete |
| `backend/app/api/routes/chat.py` | Per-user profile cache (5-min TTL); multi-SG support (`security_group_ids: List[int]`); fixed circular import — `Request` injected, `request.app.state.guardrails` used instead of `from app.main import app` |
| `backend/app/api/routes/users.py` | Cache invalidation on user/SG changes, `POST /{id}/reset-password` |
| `backend/app/api/routes/security.py` | Cache invalidation on SG/RLS/CLS changes |
| `backend/app/api/routes/geo_domain.py` | Cache invalidation on domain/subdomain/geo changes |
| `backend/app/api/routes/auth.py` | `POST /change-password`, `GET /me` returns full enriched profile |
| `backend/app/schemas/schemas.py` | `SendPromptRequest` extended with `security_group_ids: Optional[List[int]]` |

### Frontend
| File | Change |
|------|--------|
| `frontend/src/contexts/AuthContext.jsx` | Dark mode state + `toggleTheme()` |
| `frontend/src/components/layout/AppShell.jsx` | Branding: "DataMind / Decision Minds"; collapsible sidebar (hamburger toggle — collapsed shows icon-only nav + Menu button only); full user name + role in footer; role-based nav |
| `frontend/src/styles/global.css` | Decision Minds color palette: `--brand-primary: #1A4FA0`, `--brand-orange: #F47920`; two-panel signin layout; collapsed sidebar CSS; chat recent-strip CSS; `.btn-accent` orange variant |
| `frontend/src/pages/SignIn.jsx` | Two-panel layout: left branding (DataMind, Powered by Decision Minds, 4 feature cards); right form; password show/hide toggle; forgot password modal |
| `frontend/src/pages/AdminPages.jsx` | User role: read-only profile card + Change Password modal; Admin: Reset Password button per row |
| `frontend/src/pages/Chats.jsx` | Full-width chat (no left sidebar); SG multiselect chip bar (user's assigned SGs pre-selected, orange active state); recent chats collapsible strip below input; sends `security_group_ids` array |
| `frontend/src/api/client.js` | `changePassword()`, `resetUserPassword()`, `updateRLS()`, `updateCLS()`, `removeSecurityGroup()` |
| `frontend/src/main.jsx` | Routes cleaned up |

## Color Palette (Decision Minds)
| Token | Value | Use |
|-------|-------|-----|
| `--brand-primary` | `#1A4FA0` | Nav active, buttons, links |
| `--brand-primary-hover` | `#153E82` | Hover states |
| `--brand-orange` | `#F47920` | Active SG chips, accent CTAs |
| `--brand-orange-hover` | `#D9660D` | Orange hover |

## Security Payload Structure
```json
{
  "user_id": "USR003",
  "role": "Admin",
  "security_groups": ["AnalyticsTeam"],
  "domains": [{"id": 1, "name": "Sales"}],
  "subdomains": [{"id": 1, "name": "CustomerSales"}],
  "geographies": [{"id": 1, "name": "India"}],
  "row_level_security": [{"name": "...", "table": "...", "filter": "..."}],
  "column_level_security": [{"name": "...", "table": "...", "columns": [{"column": "...", "can_read": true, "can_write": false}]}]
}
```

## Resume
- Run backend: `cd backend && uvicorn app.main:app --reload --port 8000`
- Run frontend: `cd frontend && npm run dev`
- Default admin: `admin@slm.local` / `Admin@1234`
