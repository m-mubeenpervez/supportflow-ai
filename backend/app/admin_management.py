"""Role-enforced staff/customer administration and immutable operational events."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .admin_dependencies import get_current_admin, require_super_admin
from .admin_provisioning import prepare_admin_credentials, AdminProvisioningError
from .db import Session
from .models import AdminUser, Customer, Ticket, Order, EmailOutbox, Notification
from .customer_removal import anonymize_customer_account
from .customer_account_email import (
    eligible_address, queue_customer_account_notice, cancel_prior_account_notices,
)
from .admin_activity import AdminActivity

router = APIRouter(prefix="/admin/management", tags=["Admin Management"])


def public_admin(account: AdminUser):
    return {
        "id": account.id, "email": account.email, "role": account.role,
        "is_active": account.is_active, "created_at": account.created_at,
    }


def event(actor, action, entity_type, entity_id, description):
    return AdminActivity(
        actor_id=actor.id, actor_email=actor.email,
        action=action, entity_type=entity_type,
        entity_id=entity_id, description=description,
    )


class CreateAdmin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)


class AccountAction(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


@router.get('/admins')
async def list_admins(
    search: str = Query('', max_length=120),
    status: Literal['all', 'active', 'inactive'] = 'all',
    date_from: str = Query('', max_length=10),
    date_to: str = Query('', max_length=10),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    _actor: AdminUser = Depends(require_super_admin),
):
    start, end = parse_dates(date_from, date_to)
    query = select(AdminUser).where(AdminUser.role == 'admin')
    if search.strip():
        search_term = '%' + search.strip().replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.where(AdminUser.email.ilike(search_term, escape='\\'))
    if status != 'all':
        query = query.where(AdminUser.is_active.is_(status == 'active'))
    if start:
        query = query.where(func.date(func.timezone('Asia/Karachi', AdminUser.created_at)) >= start)
    if end:
        query = query.where(func.date(func.timezone('Asia/Karachi', AdminUser.created_at)) <= end)
    async with Session() as db:
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        rows = (await db.scalars(query.order_by(AdminUser.id.desc()).offset(offset).limit(limit))).all()
    return {'total': total or 0, 'admins': [public_admin(x) for x in rows]}


def parse_dates(start, end):
    from datetime import date
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
    except ValueError:
        raise HTTPException(422, 'Invalid YYYY-MM-DD date')
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, 'Start date cannot exceed end date')
    return start_date, end_date


@router.post('/admins', status_code=201)
async def create_admin(data: CreateAdmin, actor: AdminUser = Depends(require_super_admin)):
    try:
        email, password_hash = prepare_admin_credentials(str(data.email), data.password)
    except AdminProvisioningError as exc:
        raise HTTPException(422, str(exc)) from None
    async with Session() as db:
        if await db.scalar(select(AdminUser.id).where(AdminUser.email == email)) is not None:
            raise HTTPException(409, 'Administrator already exists')
        account = AdminUser(email=email, password_hash=password_hash, role='admin', is_active=True, session_version=0)
        db.add(account)
        try:
            await db.flush()
            db.add(event(actor, 'admin_created', 'admin', account.id, 'Normal administrator created'))
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(409, 'Administrator already exists') from None
        await db.refresh(account)
        return public_admin(account)


@router.post('/admins/{admin_id}/status')
async def change_admin_status(
    admin_id: int, data: AccountAction,
    active: bool, actor: AdminUser = Depends(require_super_admin)
):
    async with Session() as db:
        target = await db.scalar(select(AdminUser).where(AdminUser.id == admin_id).with_for_update())
        if target is None or target.role != 'admin':
            raise HTTPException(404, 'Normal administrator not found')
        if target.is_active == active:
            raise HTTPException(409, 'Administrator already has this status')
        target.is_active = active
        target.session_version += 1  # immediately invalidates old sessions
        db.add(event(actor, 'admin_activated' if active else 'admin_deactivated', 'admin', target.id, data.reason))
        await db.commit()
        return public_admin(target)


@router.delete('/admins/{admin_id}')
async def remove_admin(admin_id: int, data: AccountAction, actor: AdminUser = Depends(require_super_admin)):
    """Only delete inactive normal admin; preserve email in activity ledger."""
    async with Session() as db:
        target = await db.scalar(select(AdminUser).where(AdminUser.id == admin_id).with_for_update())
        if target is None or target.role != 'admin':
            raise HTTPException(404, 'Normal administrator not found')
        if target.is_active:
            raise HTTPException(409, 'Deactivate administrator before deletion')
        db.add(event(actor, 'admin_deleted', 'admin', target.id, f'{target.email}: {data.reason}'))
        await db.delete(target)
        await db.commit()
        return {'deleted': True}


@router.get('/activity')
async def admin_activity(
    admin_id: int | None = Query(None, ge=1),
    action: str = Query('', max_length=60),
    date_from: str = Query('', max_length=10),
    date_to: str = Query('', max_length=10),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=1000000),
    _actor: AdminUser = Depends(require_super_admin),
):
    start, end = parse_dates(date_from, date_to)
    query = select(AdminActivity)
    if admin_id is not None:
        query = query.where(AdminActivity.actor_id == admin_id)
    if action.strip():
        query = query.where(AdminActivity.action == action.strip())
    if start:
        query = query.where(func.date(func.timezone('Asia/Karachi', AdminActivity.created_at)) >= start)
    if end:
        query = query.where(func.date(func.timezone('Asia/Karachi', AdminActivity.created_at)) <= end)
    async with Session() as db:
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        rows = (await db.scalars(query.order_by(AdminActivity.id.desc()).offset(offset).limit(limit))).all()
    return {'total': total or 0, 'events': [
        {'id': x.id, 'actor_id': x.actor_id, 'actor_email': x.actor_email,
         'action': x.action, 'entity_type': x.entity_type, 'entity_id': x.entity_id,
         'description': x.description, 'created_at': x.created_at}
        for x in rows
    ]}


@router.get('/customers/{customer_id}')
async def customer_details(customer_id: int, _actor: AdminUser = Depends(get_current_admin)):
    async with Session() as db:
        c = await db.get(Customer, customer_id)
        if c is None or c.deleted_at is not None:
            raise HTTPException(404, 'Customer not found')
        ticket_count = await db.scalar(select(func.count(Ticket.id)).where(Ticket.customer_id == customer_id))
        order_count = await db.scalar(select(func.count(Order.id)).where(Order.customer_id == customer_id))
        return {'id': c.id, 'name': c.name, 'email': c.email,
                'is_verified': c.email_verified_at is not None,
                'is_active': c.deactivated_at is None, 'created_at': c.created_at,
                'ticket_count': ticket_count or 0, 'order_count': order_count or 0}


@router.post('/customers/{customer_id}/status')
async def change_customer_status(
    customer_id: int, data: AccountAction, active: bool,
    actor: AdminUser = Depends(get_current_admin),
):
    async with Session() as db:
        c = await db.scalar(select(Customer).where(Customer.id == customer_id).with_for_update())
        if c is None or c.deleted_at is not None:
            raise HTTPException(404, 'Customer not found')
        currently_active = c.deactivated_at is None
        if currently_active == active:
            raise HTTPException(409, 'Customer already has this status')
        if not active:
            pending = await db.scalar(select(func.count(Ticket.id)).where(
                Ticket.customer_id == customer_id, Ticket.status == 'pending_approval'))
            if pending:
                raise HTTPException(409, 'Resolve pending approvals before deactivation')
            # The ORM uses the active schema/search_path in isolated tests;
            # the production connection resolves these tables in public.
            pending_emails = await db.scalar(
                select(func.count(EmailOutbox.id))
                .join(Notification, EmailOutbox.notification_id == Notification.id)
                .where(
                    Notification.customer_id == customer_id,
                    EmailOutbox.status.in_(['pending', 'retry', 'processing']),
                )
            )
            if pending_emails:
                raise HTTPException(409, 'Customer notification emails are still processing')
        recipient = eligible_address(c)
        c.deactivated_at = None if active else datetime.now(timezone.utc)
        c.session_version += 1
        await queue_customer_account_notice(
            db, customer_id=c.id, email=recipient,
            kind='activated' if active else 'deactivated',
            event_key=f"customer:{c.id}:account:{c.session_version}:{'active' if active else 'inactive'}",
        )
        db.add(event(actor, 'customer_activated' if active else 'customer_deactivated', 'customer', c.id, data.reason))
        await db.commit()
        return {'id': c.id, 'is_active': active}


@router.delete('/customers/{customer_id}')
async def delete_customer(
    customer_id: int,
    data: AccountAction,
    actor: AdminUser = Depends(get_current_admin),
):
    """Option A: anonymize the account and preserve tickets/orders/messages.

    Actor permission is enforced by the shared JWT dependency; both staff
    and super admins are allowed to remove eligible deactivated accounts.
    """
    async with Session() as db:
        async with db.begin():
            customer = await db.scalar(
                select(Customer).where(Customer.id == customer_id).with_for_update()
            )
            if customer is None or customer.deleted_at is not None:
                raise HTTPException(404, 'Customer not found')
            original_recipient = eligible_address(customer)
            result = await anonymize_customer_account(db, customer)
            await cancel_prior_account_notices(db, customer_id)
            await queue_customer_account_notice(
                db, customer_id=customer_id, email=original_recipient,
                kind='removed', event_key=f"customer:{customer_id}:account:removed",
            )
            db.add(event(
                actor, 'customer_account_removed', 'customer', customer_id,
                f'Account anonymized; support history retained. Reason: {data.reason}',
            ))
        return result
