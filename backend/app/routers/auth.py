from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import current_user
from app.models import Membership, User, Workspace
from app.security import create_token, hash_password, login_limiter, verify_password
from app.services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=200)


class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=200)
    workspace_name: str = Field(min_length=1, max_length=120)
    timezone: str = "UTC"


def me_payload(db: Session, user: User) -> dict:
    rows = db.execute(
        select(Membership, Workspace)
        .join(Workspace, Workspace.id == Membership.workspace_id)
        .where(Membership.user_id == user.id)
        .order_by(Workspace.id)
    ).all()
    return {
        "user": {"id": user.id, "email": user.email, "name": user.name},
        "workspaces": [{"id": w.id, "name": w.name, "role": m.role, "team": m.team, "is_demo": w.is_demo, "timezone": w.timezone} for m, w in rows],
    }


@router.post("/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    key = f"{request.client.host if request.client else '?'}:{body.email.lower()}"
    if not login_limiter.allow(key, get_settings().login_attempts_per_minute):
        raise HTTPException(429, "Too many sign-in attempts. Wait a minute and try again")
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect")
    return {"token": create_token(user.id), **me_payload(db, user)}


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if not get_settings().allow_signup:
        raise HTTPException(403, "Sign-up is disabled")
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    ws = Workspace(name=body.workspace_name.strip(), timezone=body.timezone, settings={"quiet_start": "21:00", "quiet_end": "08:00"})
    db.add_all([user, ws])
    db.flush()
    db.add(Membership(user_id=user.id, workspace_id=ws.id, role="owner"))
    audit(db, ws.id, user.name, "workspace.created", "workspace", ws.id)
    db.commit()
    return {"token": create_token(user.id), **me_payload(db, user)}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return me_payload(db, user)
