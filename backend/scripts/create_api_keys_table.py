#!/usr/bin/env python3
"""
Script: create_api_keys_table.py
Purpose: Creates the llmwatch_api_keys DynamoDB table with required GSIs.
WHY: This table stores API key hashes (not raw keys) with O(1) PK lookup
for authentication and GSIs for listing by company and CRUD by key_id.

Usage:
    python scripts/create_api_keys_table.py

Table schema:
    PK: key_hash (S) — SHA-256 hex digest of the raw API key
    GSI company_id-index: PK=company_id (S), SK=created_at (S)
    GSI key_id-index: PK=key_id (S)

The table uses PAY_PER_REQUEST billing to avoid capacity planning.
"""

import os
import sys

# Allow running from backend/ or backend/scripts/
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

import boto3
from botocore.exceptions import ClientError
from config import settings, logger


def create_api_keys_table():
    """Create the llmwatch_api_keys DynamoDB table if it doesn't already exist."""
    resource_kwargs = {"region_name": settings.aws_region}
    if settings.aws_access_key_id:
        resource_kwargs["aws_access_key_id"] = settings.aws_access_key_id
    if settings.aws_secret_access_key:
        resource_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    dynamodb = boto3.resource("dynamodb", **resource_kwargs)
    table_name = settings.dynamodb_table_api_keys

    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "key_hash", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "key_hash", "AttributeType": "S"},
                {"AttributeName": "company_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
                {"AttributeName": "key_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "company_id-index",
                    "KeySchema": [
                        {"AttributeName": "company_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "key_id-index",
                    "KeySchema": [
                        {"AttributeName": "key_id", "KeyType": "HASH"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Wait for table to become active
        table.meta.client.get_waiter("table_exists").wait(TableName=table_name)
        print(f"Table '{table_name}' created successfully.")
        print(f"  PK: key_hash (S)")
        print(f"  GSI: company_id-index (company_id + created_at)")
        print(f"  GSI: key_id-index (key_id)")
        print(f"  Billing: PAY_PER_REQUEST")

    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"Table '{table_name}' already exists — skipping creation.")
        else:
            logger.error(f"Failed to create table: {e.response['Error']['Message']}")
            raise


if __name__ == "__main__":
    create_api_keys_table()
