from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app import models
from app.schemas.customer import CustomerCheck, CustomerCreate
from app.api.v1.auth import token_provider

router = APIRouter()


@router.post("/check")
def check_customer(data: CustomerCheck, db: Session = Depends(get_db)):
    clean_phone = data.phone.replace("-", "").strip()
    customer = db.query(models.User).filter(models.User.phone == clean_phone).first()

    if customer:
        return {"is_existing": True, "name": customer.name, "gender": customer.gender}
    return {"is_existing": False}


@router.post("/register")
def register_customer(data: CustomerCreate, db: Session = Depends(get_db)):
    target_phone = data.phone.replace("-", "").strip()

    if db.query(models.User).filter(models.User.phone == target_phone).first():
        raise HTTPException(status_code=400, detail="이미 등록된 번호입니다.")

    new_user = models.User(
        name=data.name, 
        gender=data.gender, 
        phone=target_phone
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "status": "success",
        "customer_id": new_user.id,
        "registered_phone": new_user.phone,
        "access_token": token_provider.encode(new_user.id),
        "token_type": "bearer"
    }