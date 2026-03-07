"""
Module: dynamo_service.py
Purpose: Handles all interactions with AWS DynamoDB.
WHY: Encapsulating database logic isolates the AWS SDK (boto3) from the rest of the app,
making it easier to test, secure, and change underlying DB models in the future.
"""
import boto3
from botocore.exceptions import ClientError
from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime
from config import settings, logger
from exceptions import DatabaseException, ResourceNotFoundException

class DynamoDBService:
    """Service to interact with DynamoDB securely."""
    
    def __init__(self):
        # WHY: We instantiate the resource once per service lifecycle to reuse HTTP connections.
        try:
            self.dynamodb = boto3.resource(
                'dynamodb',
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key
            )
            self.logs_table = self.dynamodb.Table(settings.dynamodb_table_logs)
            self.users_table = self.dynamodb.Table(settings.dynamodb_table_users)
        except Exception as e:
            logger.error(f"Failed to initialize DynamoDB client: {str(e)}")
            raise DatabaseException("Failed to establish database connection.")

    def save_log(self, company_id: str, log_data: Dict[str, Any]) -> str:
        """
        Saves an LLM interaction log to DynamoDB.
        
        Args:
            company_id (str): The PK of the logs table.
            log_data (Dict[str, Any]): The metric content to be saved.
            
        Returns:
            str: The generated log_id.
            
        Raises:
            DatabaseException: When the underlying PutItem request fails.
        """
        # WHY: Ensuring SK uniqueness using a composite format
        timestamp = datetime.utcnow().isoformat()
        log_id = str(uuid.uuid4())
        sk = f"{timestamp}#{log_id}"
        
        item = {
            'company_id': company_id,
            'timestamp#log_id': sk,
            'log_id': log_id,
            'timestamp': timestamp,
            **log_data
        }
        
        try:
            self.logs_table.put_item(Item=item)
            return log_id
        except ClientError as e:
            # WHY: Masking raw AWS exceptions to prevent exposing internal architecture
            logger.error(f"DynamoDB PutItem error: {e.response['Error']['Message']}")
            raise DatabaseException("Failed to save log entry.")

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Fetches a user record using the Global Secondary Index on email.
        
        Args:
            email (str): The user's email address.
            
        Returns:
            Optional[Dict[str, Any]]: User object if found, None otherwise.
            
        Raises:
            DatabaseException: If query operation fails.
        """
        try:
            # WHY: Parameterized Query avoids injection attacks. No string concatenation used.
            response = self.users_table.query(
                IndexName='email-index',
                KeyConditionExpression='email = :email_val',
                ExpressionAttributeValues={
                    ':email_val': email
                }
            )
            items = response.get('Items', [])
            return items[0] if items else None
        except ClientError as e:
            logger.error(f"DynamoDB Query error for email lookup: {e.response['Error']['Message']}")
            raise DatabaseException("Failed to query user by email.")
            
    def get_logs(self, company_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches the most recent logs for a company.
        
        Args:
            company_id (str): The associated company.
            limit (int): Max items to return.
            
        Returns:
            List[Dict[str, Any]]: List of log entries.
            
        Raises:
            DatabaseException: If the query fails.
        """
        try:
            response = self.logs_table.query(
                KeyConditionExpression='company_id = :comp_id',
                ExpressionAttributeValues={
                    ':comp_id': company_id
                },
                ScanIndexForward=False, # Descending sort (newest first)
                Limit=limit
            )
            return response.get('Items', [])
        except ClientError as e:
            logger.error(f"DynamoDB get_logs error: {e.response['Error']['Message']}")
            raise DatabaseException("Failed to retrieve logs.")

dynamo_service = DynamoDBService()
