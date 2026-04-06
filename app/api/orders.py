from fastapi import APIRouter, Header, Request, status, Response
from typing import Optional
from app.schemas.order import OrderCreate, OrderResponse
from app.services.order_service import create_order_idempotent

router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("/", response_model=OrderResponse)
async def create_order(
    request: Request,
    response: Response,
    order: OrderCreate
):
    pool = request.app.state.pool
    
    result = await create_order_idempotent(pool, order)
    
    if result["is_existing"]:
        response.status_code = status.HTTP_200_OK
    else:
        response.status_code = status.HTTP_201_CREATED
        
    return result
