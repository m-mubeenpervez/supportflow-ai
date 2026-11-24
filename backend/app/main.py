from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import JSONResponse
from .auth import decode_access_token, decode_access_token_version
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from .config import settings
from .db import Session, init_db
from .models import Customer, Order, Ticket, Message, Audit, Notification

from .notification_service import (
    notify_admin_approval_requested,
    active_admin_notification_recipients,
    notify_customer_decision,
)
from .email_recipients import (
    admin_notification_recipient,
    customer_notification_recipient,
)
from .graph import graph

from sqlalchemy.exc import IntegrityError

from .auth import (
    hash_password,
    verify_password,
    create_access_token,
)
from .auth_schemas import (
    CustomerRegister,
    CustomerLogin,
    TokenResponse,
)
from .verification_registration import register_customer_with_verification
from .verification_runtime_config import get_verification_email_config
from .verification_routes import router as verification_router
from .admin_routes import router as admin_auth_router
from .admin_management import router as admin_management_router
from .admin_dependencies import get_current_admin
from .verification_email_queue import queue_verification_email
from .email_verification_service import (
    AlreadyVerifiedError,
    VerificationCooldownError,
)



@asynccontextmanager
async def lifespan(app:FastAPI):
    await init_db()
    yield
app=FastAPI(title='SupportFlow AI',version='0.1.0',lifespan=lifespan)

# Admin JWT endpoints remain disabled by default.
if settings.admin_jwt_routes_enabled:
    app.include_router(admin_auth_router)
    app.include_router(admin_management_router)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins.split(','),allow_methods=['*'],allow_headers=['*'])

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_customer(
    credentials: HTTPAuthorizationCredentials | None = Security(
        bearer_scheme
    ),
) -> Customer:
    """Identify customer using a verified JWT."""

    unauthorized = HTTPException(
        status_code=401,
        detail="Invalid or missing authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    customer_id = decode_access_token(credentials.credentials)

    if customer_id is None:
        raise unauthorized

    async with Session() as db:
        customer = await db.get(Customer, customer_id)

        if (
            customer is None
            or not customer.password_hash
            or customer.deactivated_at is not None
        ):
            raise unauthorized

        token_version = decode_access_token_version(
            credentials.credentials
        )

        if (
            token_version is None
            or token_version != customer.session_version
        ):
            raise unauthorized

        return customer




def require_verified_customer(
    customer: Customer = Depends(get_current_customer),
) -> Customer:
    """Allow customer operations only after email verification."""

    if customer.email_verified_at is None:
        raise HTTPException(
            status_code=403,
            detail="Email verification required",
        )

    return customer



class ChatIn(BaseModel):
    message: str = Field(min_length=2, max_length=3000)
    ticket_id: int | None = None

class Decision(BaseModel):
    approve:bool
    note:str=Field(default='',max_length=500)

def legacy_admin(x_admin_token: str = Header(default="")):
    """Legacy admin auth, used only while JWT rollout is disabled."""
    if not x_admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(403, "Admin authorization required")


# Choose the dependency once at application startup. When JWT mode is
# enabled, the shared X-Admin-Token cannot authorize ANY admin endpoint.
admin = get_current_admin if settings.admin_jwt_routes_enabled else legacy_admin


@app.post("/auth/register", status_code=201)
async def register(data: CustomerRegister):
    """Atomically register customer and queue verification."""

    try:
        runtime = get_verification_email_config()
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="Email verification is temporarily unavailable",
        ) from None

    try:
        async with Session() as db:
            async with db.begin():
                result = await register_customer_with_verification(
                    db,
                    name=data.name,
                    email=str(data.email),
                    password=data.password,
                    encryption_key=runtime.encryption_key,
                )

        return result

    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        ) from None


@app.post("/auth/login", response_model=TokenResponse)
async def login(data: CustomerLogin):
    """Authenticate customer and issue JWT access token."""

    email = str(data.email).lower()

    async with Session() as db:
        customer = await db.scalar(
            select(Customer).where(Customer.email == email)
        )

        if (
            customer is None
            or customer.deactivated_at is not None
            or not customer.password_hash
            or not verify_password(
                data.password,
                customer.password_hash,
            )
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = create_access_token(customer.id, customer.session_version)

        return TokenResponse(
            access_token=token,
            token_type="bearer",
        )

@app.post("/auth/resend-verification", status_code=202)
async def resend_verification(
    customer: Customer = Depends(get_current_customer),
):
    """Queue another verification email for the authenticated user."""

    try:
        runtime = get_verification_email_config()
    except RuntimeError:
        raise HTTPException(
            status_code=503,
            detail="Email verification is temporarily unavailable",
        ) from None

    try:
        async with Session() as db:
            async with db.begin():
                await queue_verification_email(
                    db,
                    customer_id=customer.id,
                    encryption_key=runtime.encryption_key,
                )
    except VerificationCooldownError:
        raise HTTPException(
            status_code=429,
            detail="Please wait before requesting another verification email",
        ) from None
    except AlreadyVerifiedError:
        raise HTTPException(
            status_code=409,
            detail="Email address is already verified",
        ) from None

    return {"message": "Verification email queued"}



class AccountDeactivationRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
    confirmation: str


@app.post("/auth/deactivate-account")
async def deactivate_my_account(
    data: AccountDeactivationRequest,
    customer: Customer = Depends(require_verified_customer),
):
    """Password-confirmed customer account deactivation.

    This is not permanent personal-data erasure.
    Existing orders, tickets and audit records are retained.
    """
    if data.confirmation != "DEACTIVATE":
        raise HTTPException(
            status_code=400,
            detail="Explicit confirmation required",
        )

    async with Session() as db:
        async with db.begin():
            account = await db.scalar(
                select(Customer)
                .where(Customer.id == customer.id)
                .with_for_update()
            )

            if account is None or account.deactivated_at is not None:
                raise HTTPException(
                    status_code=401,
                    detail="Account unavailable",
                )

            if (
                not account.password_hash
                or not verify_password(
                    data.password, account.password_hash
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Incorrect password",
                )

            # Protect unresolved approval workflows.
            pending_ticket = await db.scalar(
                select(Ticket.id)
                .where(
                    Ticket.customer_id == account.id,
                    Ticket.status == "pending_approval",
                )
                .limit(1)
            )

            if pending_ticket is not None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Resolve pending approval requests "
                        "before deactivating this account."
                    ),
                )

            # Do not deactivate while customer notification
            # emails are still pending or being delivered.
            from sqlalchemy import text

            pending_email_count = await db.scalar(
                text("""
                    SELECT COUNT(*)
                    FROM public.email_outbox e
                    JOIN public.notifications n
                      ON n.id = e.notification_id
                    WHERE n.customer_id = :customer_id
                      AND e.status IN (
                        'pending', 'retry', 'processing'
                      )
                """),
                {"customer_id": account.id},
            )

            if pending_email_count:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Account notifications are still being "
                        "processed. Please try again later."
                    ),
                )

            account.deactivated_at = datetime.now(timezone.utc)

    return {
        "deactivated": True,
        "message": (
            "Your account has been deactivated. "
            "You can no longer sign in."
        ),
    }


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=1, max_length=128)


@app.post("/auth/change-password")
async def change_my_password(
    data: ChangePasswordRequest,
    customer: Customer = Depends(require_verified_customer),
):
    """Change password and invalidate earlier customer sessions."""
    if data.new_password != data.confirm_password:
        raise HTTPException(
            status_code=400,
            detail="New passwords do not match",
        )

    from .password_policy import password_policy_errors

    errors = password_policy_errors(data.new_password)

    if errors:
        raise HTTPException(
            status_code=400,
            detail="; ".join(errors),
        )

    async with Session() as db:
        async with db.begin():
            account = await db.scalar(
                select(Customer)
                .where(Customer.id == customer.id)
                .with_for_update()
            )

            if (
                account is None
                or account.deactivated_at is not None
                or not account.password_hash
            ):
                raise HTTPException(
                    status_code=401,
                    detail="Account unavailable",
                )

            if not verify_password(
                data.current_password,
                account.password_hash,
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Current password is incorrect",
                )

            if verify_password(
                data.new_password,
                account.password_hash,
            ):
                raise HTTPException(
                    status_code=400,
                    detail="New password must be different",
                )

            account.password_hash = hash_password(
                data.new_password
            )
            account.session_version += 1

    return {
        "password_changed": True,
        "message": "Password changed. Please sign in again.",
    }


@app.get("/auth/me")
async def get_my_account(
    customer: Customer = Depends(require_verified_customer),
):
    """Return the authenticated customer's safe profile fields."""
    return {
        "id": customer.id,
        "name": customer.name,
        "email": customer.email,
        "email_verified": customer.email_verified_at is not None,
    }


@app.get("/auth/verification-status")
async def verification_status(
    customer: Customer = Depends(get_current_customer),
):
    """Return email verification state for an authenticated customer."""

    return JSONResponse(
        content={
            "email_verified": customer.email_verified_at is not None
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get('/health')
async def health():return {'status':'ok'}


@app.post("/chat")
async def chat(
    data: ChatIn,
    customer: Customer = Depends(require_verified_customer),
):
    """Process a support message for the authenticated customer."""

    customer_id = customer.id

    async with Session() as db:
        if data.ticket_id is not None:
            ticket = await db.scalar(
                select(Ticket).where(
                    Ticket.id == data.ticket_id,
                    Ticket.customer_id == customer_id,
                    Ticket.customer_hidden_at.is_(None),
                )
            )

            if ticket is None:
                raise HTTPException(
                    status_code=404,
                    detail="Ticket not found",
                )

            if ticket.status != "open":
                raise HTTPException(
                    status_code=409,
                    detail="Ticket is not open",
                )
        else:
            ticket = Ticket(
                customer_id=customer_id,
                summary=data.message[:300],
            )
            db.add(ticket)
            await db.flush()

        # Existing conversation only; ticket ownership verified above.
        previous_messages = []
        if data.ticket_id is not None:
            recent = (
                await db.scalars(
                    select(Message)
                    .where(Message.ticket_id == ticket.id)
                    .order_by(Message.id.desc())
                    .limit(12)
                )
            ).all()

            previous_messages = [
                {"role": row.role, "content": row.content}
                for row in reversed(recent)
                if row.role in {"user", "assistant"}
            ]

        result = await graph.ainvoke(
            {
                "message": data.message,
                "customer_id": customer_id,
                "history": previous_messages,
                # The ticket was ownership-checked above; carrying its
                # verified order id supports safe multi-turn follow-ups.
                "order_id": ticket.order_id,
            }
        )

        ticket.intent = result["intent"]
        ticket.order_id = (
            result.get("order_id") or ticket.order_id
        )
        ticket.response = result["draft"]
        ticket.status = (
            "pending_approval"
            if result["needs_approval"]
            else "open"
        )

        db.add(
            Message(
                ticket_id=ticket.id,
                role="user",
                content=data.message,
            )
        )

        db.add(
            Message(
                ticket_id=ticket.id,
                role="assistant",
                content=result["draft"],
            )
        )

        db.add(
            Audit(
                ticket_id=ticket.id,
                action="draft_created",
                details=result["intent"],
            )
        )

        # Persist admin notification with the ticket transaction.
        if ticket.status == "pending_approval":
            await notify_admin_approval_requested(
                db,
                ticket=ticket,
                admin_emails=await active_admin_notification_recipients(db),
                admin_email=admin_notification_recipient(),
            )

        await db.commit()
        await db.refresh(ticket)

        return {
            "ticket_id": ticket.id,
            "intent": ticket.intent,
            "status": ticket.status,
            "reply": ticket.response,
            "sources": result["sources"],
        }



# ==========================================================
# CUSTOMER CONVERSATION HISTORY
# ==========================================================

@app.get("/customer/tickets")
async def customer_tickets(
    customer: Customer = Depends(require_verified_customer),
):
    """Return tickets belonging to the authenticated customer."""

    async with Session() as db:
        rows = (
            await db.scalars(
                select(Ticket)
                .where(
                    Ticket.customer_id == customer.id,
                    Ticket.customer_hidden_at.is_(None),
                )
                .order_by(Ticket.created_at.desc(), Ticket.id.desc())
                .limit(100)
            )
        ).all()

        return [
            {
                "id": ticket.id,
                "summary": ticket.summary,
                "intent": ticket.intent,
                "status": ticket.status,
                "order_id": ticket.order_id,
                "created_at": ticket.created_at,
            }
            for ticket in rows
        ]



@app.delete("/customer/tickets/{ticket_id}")
async def remove_customer_conversation(
    ticket_id: int,
    customer: Customer = Depends(require_verified_customer),
):
    """Remove only the authenticated customer's chat from history."""
    from datetime import datetime, timezone

    async with Session() as db:
        ticket = await db.scalar(
            select(Ticket).where(
                Ticket.id == ticket_id,
                Ticket.customer_id == customer.id,
                Ticket.customer_hidden_at.is_(None),
            )
        )

        if ticket is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found",
            )

        ticket.customer_hidden_at = datetime.now(timezone.utc)

        await db.commit()

        return {
            "success": True,
            "ticket_id": ticket_id,
            "message": "Conversation removed from your history",
        }


@app.get("/customer/tickets/{ticket_id}/messages")
async def customer_ticket_messages(
    ticket_id: int,
    customer: Customer = Depends(require_verified_customer),
):
    """Return messages only when the ticket belongs to the customer."""

    async with Session() as db:
        ticket = await db.scalar(
            select(Ticket).where(
                Ticket.id == ticket_id,
                Ticket.customer_id == customer.id,
                Ticket.customer_hidden_at.is_(None),
            )
        )

        if ticket is None:
            raise HTTPException(
                status_code=404,
                detail="Ticket not found",
            )

        rows = (
            await db.scalars(
                select(Message)
                .where(Message.ticket_id == ticket.id)
                .order_by(Message.id.asc())
            )
        ).all()

        return {
            "ticket_id": ticket.id,
            "status": ticket.status,
            "intent": ticket.intent,
            "messages": [
                {
                    "id": message.id,
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at,
                }
                for message in rows
            ],
        }



@app.get('/tickets', dependencies=[Depends(admin)])
async def tickets():
    async with Session() as db:
        rows = (
            await db.scalars(
                select(Ticket)
                .order_by(Ticket.id.desc())
                .limit(100)
            )
        ).all()

        return [
            {
                "id": t.id,
                "customer_id": t.customer_id,
                "order_id": t.order_id,
                "intent": t.intent,
                "status": t.status,
                "summary": t.summary,
                "response": t.response,
                "created_at": (
                    t.created_at.isoformat()
                    if t.created_at
                    else None
                ),
            }
            for t in rows
        ]


@app.get('/tickets/{ticket_id}/messages',dependencies=[Depends(admin)])
async def messages(ticket_id:int):
    async with Session() as db:
        rows=(await db.scalars(select(Message).where(Message.ticket_id==ticket_id).order_by(Message.id))).all()
        return [{'role':m.role,'content':m.content} for m in rows]

@app.post('/tickets/{ticket_id}/decision')
async def decision(ticket_id:int,data:Decision, actor=Depends(admin)):
    async with Session() as db:
        # Lock the ticket row until the decision transaction commits.
        t = await db.scalar(
            select(Ticket)
            .where(Ticket.id == ticket_id)
            .with_for_update()
        )

        if not t:
            raise HTTPException(404, 'Ticket not found')

        if t.status != 'pending_approval':
            raise HTTPException(
                409,
                'Ticket is not awaiting approval',
            )

        t.approved = data.approve
        t.status = 'approved' if data.approve else 'rejected'
        db.add(Audit(ticket_id=t.id,action=t.status,details=data.note))
        if settings.admin_jwt_routes_enabled:
            from .admin_activity import AdminActivity
            db.add(AdminActivity(
                actor_id=actor.id, actor_email=actor.email,
                action='ticket_approved' if data.approve else 'ticket_rejected',
                entity_type='ticket', entity_id=t.id,
                description='Human review decision recorded',
            ))

        # The recipient is resolved from the ticket owner in the DB,
        # never from request data or the administrator's input.
        ticket_owner = await db.get(Customer, t.customer_id)
        await notify_customer_decision(
            db,
            ticket=t,
            customer_email=customer_notification_recipient(ticket_owner),
        )

        await db.commit()
        return {'id':t.id,'status':t.status,'note':'Approval records decision only; no financial or cancellation action is executed.'}


# ==========================================================
# SECURE IN-APP NOTIFICATIONS
# ==========================================================

def serialize_notification(notification):
    return {
        "id": notification.id,
        "ticket_id": notification.ticket_id,
        "event_type": notification.event_type,
        "title": notification.title,
        "body": notification.body,
        "created_at": notification.created_at,
        "read_at": notification.read_at,
    }


@app.get("/notifications/admin", dependencies=[Depends(admin)])
async def admin_notifications():
    """Return recent administrator notifications."""

    async with Session() as db:
        notifications = (
            await db.scalars(
                select(Notification)
                .where(Notification.recipient_type == "admin")
                .order_by(Notification.id.desc())
                .limit(100)
            )
        ).all()

        return [
            serialize_notification(notification)
            for notification in notifications
        ]


@app.post(
    "/notifications/admin/{notification_id}/read",
    dependencies=[Depends(admin)],
)
async def mark_admin_notification_read(notification_id: int):
    """Mark an administrator notification as read."""

    async with Session() as db:
        notification = await db.scalar(
            select(Notification)
            .where(
                Notification.id == notification_id,
                Notification.recipient_type == "admin",
            )
            .with_for_update()
        )

        if notification is None:
            raise HTTPException(404, "Notification not found")

        if notification.read_at is None:
            notification.read_at = datetime.now(timezone.utc)
            await db.commit()

        return serialize_notification(notification)


@app.get("/notifications/customer")
async def customer_notifications(
    customer: Customer = Depends(require_verified_customer),
):
    """Return notifications owned by the authenticated customer."""

    async with Session() as db:
        notifications = (
            await db.scalars(
                select(Notification)
                .where(
                    Notification.recipient_type == "customer",
                    Notification.customer_id == customer.id,
                )
                .order_by(Notification.id.desc())
                .limit(100)
            )
        ).all()

        return [
            serialize_notification(notification)
            for notification in notifications
        ]


@app.post("/notifications/customer/{notification_id}/read")
async def mark_customer_notification_read(
    notification_id: int,
    customer: Customer = Depends(require_verified_customer),
):
    """Prevent customers from accessing other users' notifications."""

    async with Session() as db:
        notification = await db.scalar(
            select(Notification)
            .where(
                Notification.id == notification_id,
                Notification.recipient_type == "customer",
                Notification.customer_id == customer.id,
            )
            .with_for_update()
        )

        if notification is None:
            raise HTTPException(404, "Notification not found")

        if notification.read_at is None:
            notification.read_at = datetime.now(timezone.utc)
            await db.commit()

        return serialize_notification(notification)


@app.post('/demo/seed',dependencies=[Depends(admin)])
async def seed():
    async with Session() as db:
        c=await db.scalar(select(Customer).where(Customer.email=='demo@example.com'))
        if not c:
            c=Customer(name='Demo Customer',email='demo@example.com');db.add(c);await db.flush()
        if not await db.get(Order,'ORD1023'):
            db.add(Order(id='ORD1023',customer_id=c.id,item='Wireless Headphones',status='delivered',total=4999))
        await db.commit()
        return {'customer_id':c.id,'order_id':'ORD1023'}


app.include_router(verification_router)


@app.get("/admin/customers")

async def list_admin_customers(
    limit: int = 25,
    offset: int = 0,
    date_preset: str = "all",
    date_from: str = "",
    date_to: str = "",
    time_from: str = "",
    time_to: str = "",
    search: str = "",
    account_status: str = "all",
    verification_status: str = "all",
    _admin=Depends(admin),
):
    """Read-only customers filtered by registration date/time in PKT."""
    from datetime import date, datetime, time, timedelta
    from zoneinfo import ZoneInfo
    from sqlalchemy import (
        Time as SQLTime,
        and_, or_, cast, func, select,
    )

    if not 1 <= limit <= 50:
        raise HTTPException(422, "Invalid limit")

    if not 0 <= offset <= 1000000:
        raise HTTPException(422, "Invalid offset")

    if date_preset not in (
        "all", "today", "7days", "30days", "custom"
    ):
        raise HTTPException(422, "Invalid date preset")

    if date_preset != "custom" and (date_from or date_to):
        raise HTTPException(
            422, "Custom dates require the custom preset"
        )

    def read_date(value):
        if not value:
            return None
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError("Invalid format")
            return parsed
        except ValueError:
            raise HTTPException(422, "Invalid date")

    def read_time(value):
        if not value:
            return None
        try:
            parsed = time.fromisoformat(value)
            if (
                parsed.tzinfo is not None
                or len(value) != 5
                or parsed.strftime("%H:%M") != value
            ):
                raise ValueError("Invalid format")
            return parsed
        except ValueError:
            raise HTTPException(422, "Invalid time")

    today = datetime.now(
        ZoneInfo("Asia/Karachi")
    ).date()

    start = None
    end = None

    if date_preset == "today":
        start = today
        end = today

    elif date_preset == "7days":
        start = today - timedelta(days=6)
        end = today

    elif date_preset == "30days":
        start = today - timedelta(days=29)
        end = today

    elif date_preset == "custom":
        start = read_date(date_from)
        end = read_date(date_to)

    if start and end and start > end:
        raise HTTPException(
            422, "Start date cannot be after end date"
        )

    start_time = read_time(time_from)
    end_time = read_time(time_to)

    # Store UTC-aware instants, filter in Pakistan local time.
    local_timestamp = func.timezone(
        "Asia/Karachi", Customer.created_at
    )

    local_day = func.date(local_timestamp)
    local_clock = cast(local_timestamp, SQLTime())

    if len(search) > 120:
        raise HTTPException(422, "Customer search too long")
    if account_status not in ("all", "active", "deactivated"):
        raise HTTPException(422, "Invalid customer status")
    if verification_status not in ("all", "verified", "unverified"):
        raise HTTPException(422, "Invalid verification status")

    conditions = [Customer.deleted_at.is_(None)]
    if search.strip():
        escaped = search.strip().replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        matches = [Customer.email.ilike(pattern, escape="\\"),
                   Customer.name.ilike(pattern, escape="\\")]
        if search.strip().isdigit():
            matches.append(Customer.id == int(search.strip()))
        conditions.append(or_(*matches))
    if account_status != "all":
        conditions.append(Customer.deactivated_at.is_(None) if account_status == "active"
                          else Customer.deactivated_at.is_not(None))
    if verification_status != "all":
        conditions.append(Customer.email_verified_at.is_not(None) if verification_status == "verified"
                          else Customer.email_verified_at.is_(None))

    if start:
        conditions.append(local_day >= start)

    if end:
        conditions.append(local_day <= end)

    if start_time and end_time:
        if start_time <= end_time:
            conditions.append(and_(
                local_clock >= start_time,
                local_clock <= end_time,
            ))
        else:
            # Overnight window, such as 22:00 to 02:00.
            conditions.append(or_(
                local_clock >= start_time,
                local_clock <= end_time,
            ))

    elif start_time:
        conditions.append(local_clock >= start_time)

    elif end_time:
        conditions.append(local_clock <= end_time)

    async with Session() as db:
        total = await db.scalar(
            select(func.count(Customer.id))
            .where(*conditions)
        )

        query = (
            select(
                Customer.id.label("id"),
                Customer.name.label("name"),
                Customer.email.label("email"),
                Customer.email_verified_at.label(
                    "email_verified_at"
                ),
                Customer.deactivated_at.label(
                    "deactivated_at"
                ),
                Customer.created_at.label("created_at"),
                func.count(Ticket.id).label("ticket_count"),
            )
            .select_from(Customer)
            .outerjoin(
                Ticket,
                Ticket.customer_id == Customer.id
            )
            .where(*conditions)
            .group_by(Customer.id)
            .order_by(Customer.id.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await db.execute(query)
        rows = result.mappings().all()

    return {
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
        "customers": [
            {
                "id": row["id"],
                "name": row["name"],
                "email": row["email"],
                "email_verified": (
                    row["email_verified_at"] is not None
                ),
                "status": (
                    "deactivated"
                    if row["deactivated_at"] is not None
                    else "active"
                ),
                "ticket_count": int(row["ticket_count"]),
                "created_at": (
                    row["created_at"].isoformat()
                    if row.get("created_at") is not None
                    else None
                ),
            }
            for row in rows
        ],
    }
