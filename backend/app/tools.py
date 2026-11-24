from sqlalchemy import select
from .db import Session
from .models import Customer, Order, Ticket, Audit


async def get_order_details(customer_id: int, order_id: str):
    """Return order only when it belongs to the given customer."""

    async with Session() as db:
        order = await db.scalar(
            select(Order).where(
                Order.id == order_id,
                Order.customer_id == customer_id,
            )
        )

        if order is None:
            return {
                "error": "Order not found or access denied"
            }

        return {
            "id": order.id,
            "item": order.item,
            "status": order.status,
            "total": order.total,
        }


async def get_customer_details(customer_id:int):
    async with Session() as db:
        c=await db.get(Customer,customer_id)
        return {'id':c.id,'name':c.name,'email':c.email} if c else {'error':'Customer not found'}

async def get_ticket(ticket_id:int,customer_id:int):
    async with Session() as db:
        t=await db.scalar(select(Ticket).where(Ticket.id==ticket_id,Ticket.customer_id==customer_id))
        return {'id':t.id,'status':t.status,'intent':t.intent} if t else {'error':'Not found'}

async def audit(ticket_id:int,action:str,details:str=''):
    async with Session() as db:
        db.add(Audit(ticket_id=ticket_id,action=action,details=details))
        await db.commit()
