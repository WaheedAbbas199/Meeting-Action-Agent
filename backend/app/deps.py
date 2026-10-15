"""FastAPI dependencies: authentication, workspace membership, role checks."""

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ROLE_RANK, Membership, User, Workspace
from app.security import decode_token


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Sign in required")
    uid = decode_token(authorization.split(" ", 1)[1].strip())
    user = db.get(User, uid) if uid else None
    if not user or not user.is_active:
        raise HTTPException(401, "Session expired. Sign in again")
    return user


@dataclass
class Ctx:
    db: Session
    user: User
    workspace: Workspace
    membership: Membership

    @property
    def wid(self) -> int:
        return self.workspace.id

    @property
    def role(self) -> str:
        return self.membership.role

    def can(self, role: str) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[role]

    def require(self, role: str) -> None:
        if not self.can(role):
            raise HTTPException(403, f"This action needs the {role} role or higher")


def workspace_ctx(wid: int = Path(...), user: User = Depends(current_user), db: Session = Depends(get_db)) -> Ctx:
    """Resolve the workspace and verify the caller is a member. Non-members get 403."""
    m = db.scalar(select(Membership).where(Membership.user_id == user.id, Membership.workspace_id == wid))
    ws = db.get(Workspace, wid) if m else None
    if not m or not ws:
        raise HTTPException(403, "You do not have access to this workspace")
    return Ctx(db=db, user=user, workspace=ws, membership=m)


def get_owned(ctx: Ctx, model, obj_id: int):
    """Fetch an entity only if it belongs to the caller's workspace (404 otherwise, no leakage)."""
    obj = ctx.db.get(model, obj_id)
    if obj is None or getattr(obj, "workspace_id", None) != ctx.wid:
        raise HTTPException(404, f"{model.__name__} not found")
    return obj
