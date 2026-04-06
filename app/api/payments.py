from fastapi import APIRouter, Request, Response, status
from app.schemas.payment import PaymentCreate, PaymentResponse
from app.services.payment_service import generate_payment_intent

router = APIRouter(prefix="/payments", tags=["payments"])

@router.post("/", response_model=PaymentResponse)
async def create_payment(
    request: Request,
    response: Response,
    payment: PaymentCreate
):
    pool = request.app.state.pool

    payment_record = await generate_payment_intent(pool, payment)
    
    # We universally allow payment intent creation (handling overlapping successes via auto-refunds later).
    response.status_code = status.HTTP_201_CREATED

    return payment_record
