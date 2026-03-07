"""
Module: auth.py
Purpose: Exposes authentication API routes.
WHY: Encapsulating login/registration endpoints isolates public-facing handlers from protected routes.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from models.schemas import RegisterRequest, LoginRequest, TokenResponse
from auth.jwt_handler import get_password_hash, verify_password, create_access_token
from services.dynamo_service import dynamo_service
from exceptions import ValidationException
import uuid
from datetime import datetime

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register")
async def register(request: Request, data: RegisterRequest):
    """
    Registers a new company and admin user.
    """
    existing_user = dynamo_service.get_user_by_email(data.email)
    if existing_user:
        # WHY: Generic validation exception, keeping status format standardized by top-level handler
        raise ValidationException("Email already registered")
        
    company_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    hashed_pwd = get_password_hash(data.password)
    
    item = {
        "company_id": company_id,
        "email": data.email,
        "company_name": data.company_name,
        "user_id": user_id,
        "hashed_password": hashed_pwd,
        "created_at": datetime.utcnow().isoformat(),
        "is_active": True
    }
    
    # Normally we'd insert this record in DynamoDB users_table
    # Since DynamoDBService in our boilerplate didn't explicitly implement put_user, 
    # we manually call put_item on users_table for completion.
    dynamo_service.users_table.put_item(Item=item)
    
    return {"message": "User registered successfully", "company_id": company_id}

@router.post("/login", response_model=TokenResponse)
async def login(request: Request, data: LoginRequest):
    """
    Authenticates a user and issues a JWT if successful.
    """
    user = dynamo_service.get_user_by_email(data.email)
    if not user or not verify_password(data.password, user.get("hashed_password")):
        raise ValidationException("Invalid credentials")
        
    if not user.get("is_active", True):
        raise ValidationException("Account disabled")

    # WHY: Including company_id in the token prevents us from needing to hit the DB
    # on every subsequent request to figure out which tenant they belong to.
    access_token = create_access_token(
        data={"sub": user["user_id"], "company_id": user["company_id"]}
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "expires_in": 3600 * 24 # 24h
    }
