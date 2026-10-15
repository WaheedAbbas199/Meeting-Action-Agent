# API

Interactive docs (Swagger UI) are served at `/api/docs` and the schema at `/api/openapi.json` (not in the CSP-restricted app pages).

- Auth: `POST /api/auth/login` returns `{token}`; send `Authorization: Bearer <token>`.
- Workspace-scoped routes live under `/api/w/{workspace_id}/…`. Non-members get **403**; ids from another workspace get **404**.
- Errors: `{"detail": "message"}`. Business-rule violations (cycles, expired approvals, missing consent…) are **409**; validation errors are **422**; rate limit **429**.

| Method | Path | Summary |
|---|---|---|
| POST | `/api/auth/login` | Login |
| GET | `/api/auth/me` | Me |
| POST | `/api/auth/register` | Register |
| GET | `/api/health` | Health |
| GET | `/api/ready` | Ready |
| GET | `/api/w/{wid}/agendas` | List Agendas |
| POST | `/api/w/{wid}/agendas` | New Agenda |
| GET | `/api/w/{wid}/agendas/{aid}` | Get Agenda |
| PUT | `/api/w/{wid}/agendas/{aid}` | Edit Agenda |
| POST | `/api/w/{wid}/agendas/{aid}/approve` | Approve Agenda |
| POST | `/api/w/{wid}/agendas/{aid}/calendar` | Propose Event |
| GET | `/api/w/{wid}/analytics` | Get Analytics |
| GET | `/api/w/{wid}/approvals` | List Approvals |
| POST | `/api/w/{wid}/approvals/{aid}/decide` | Decide |
| POST | `/api/w/{wid}/approvals/{aid}/revoke` | Revoke |
| GET | `/api/w/{wid}/audit` | Audit Log |
| GET | `/api/w/{wid}/contacts` | List Contacts |
| POST | `/api/w/{wid}/contacts` | Create Contact |
| PUT | `/api/w/{wid}/contacts/{cid}` | Update Contact |
| DELETE | `/api/w/{wid}/contacts/{cid}` | Delete Contact |
| GET | `/api/w/{wid}/dashboard` | Dashboard |
| GET | `/api/w/{wid}/decisions` | List Decisions |
| GET | `/api/w/{wid}/decisions/{did}` | Get Decision |
| POST | `/api/w/{wid}/decisions/{did}/resolve` | Resolve |
| POST | `/api/w/{wid}/decisions/{did}/status` | Decision Status |
| GET | `/api/w/{wid}/dependency-graph` | Graph |
| GET | `/api/w/{wid}/followups` | List Followups |
| POST | `/api/w/{wid}/followups` | Create Draft |
| POST | `/api/w/{wid}/followups/run-reminders` | Run Reminders |
| PATCH | `/api/w/{wid}/followups/{fid}` | Edit Draft |
| POST | `/api/w/{wid}/followups/{fid}/retry` | Retry |
| POST | `/api/w/{wid}/followups/{fid}/submit` | Submit |
| GET | `/api/w/{wid}/integrations` | Integrations |
| PUT | `/api/w/{wid}/integrations/{kind}` | Set Integration |
| GET | `/api/w/{wid}/jobs` | Jobs Health |
| GET | `/api/w/{wid}/meetings` | List Meetings |
| POST | `/api/w/{wid}/meetings` | Create Meeting |
| POST | `/api/w/{wid}/meetings/upload` | Upload Meeting |
| GET | `/api/w/{wid}/meetings/{mid}` | Get Meeting |
| POST | `/api/w/{wid}/meetings/{mid}/retry` | Retry Meeting |
| POST | `/api/w/{wid}/meetings/{mid}/review` | Review Meeting |
| GET | `/api/w/{wid}/members` | List Members |
| POST | `/api/w/{wid}/members` | Add Member |
| PATCH | `/api/w/{wid}/members/{user_id}` | Patch Member |
| POST | `/api/w/{wid}/memory/ask` | Ask |
| GET | `/api/w/{wid}/notifications` | Notifications |
| POST | `/api/w/{wid}/notifications/read-all` | Read All |
| GET | `/api/w/{wid}/reminder-rules` | List Rules |
| POST | `/api/w/{wid}/reminder-rules` | Create Rule |
| PUT | `/api/w/{wid}/reminder-rules/{rid}` | Update Rule |
| DELETE | `/api/w/{wid}/reminder-rules/{rid}` | Delete Rule |
| GET | `/api/w/{wid}/risks` | Risks |
| GET | `/api/w/{wid}/search` | Global Search |
| GET | `/api/w/{wid}/tasks` | List Tasks |
| POST | `/api/w/{wid}/tasks` | Create Task |
| GET | `/api/w/{wid}/tasks/{tid}` | Get Task |
| PATCH | `/api/w/{wid}/tasks/{tid}` | Patch Task |
| POST | `/api/w/{wid}/tasks/{tid}/approve` | Approve |
| POST | `/api/w/{wid}/tasks/{tid}/dependencies` | Add Dep |
| DELETE | `/api/w/{wid}/tasks/{tid}/dependencies/{pid}` | Remove Dep |
| POST | `/api/w/{wid}/tasks/{tid}/reject` | Reject |
| POST | `/api/w/{wid}/tasks/{tid}/status` | Set Status |
| GET | `/api/w/{wid}/workload` | Get Workload |
| POST | `/api/w/{wid}/workload/apply` | Apply Reassignment |
| GET | `/api/w/{wid}/workspace` | Get Workspace |
| PATCH | `/api/w/{wid}/workspace` | Patch Workspace |
| GET | `/api/webhooks/whatsapp` | Whatsapp Verify |
| POST | `/api/webhooks/whatsapp` | Whatsapp Events |
