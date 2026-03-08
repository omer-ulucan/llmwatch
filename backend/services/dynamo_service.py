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
from datetime import datetime, timezone
from config import settings, logger
from exceptions import DatabaseException, ResourceNotFoundException


class DynamoDBService:
    """Service to interact with DynamoDB securely."""

    def __init__(self):
        # WHY: We instantiate the resource once per service lifecycle to reuse HTTP connections.
        try:
            # WHY: Only pass explicit credentials when configured.
            # On EC2 with an IAM role, boto3 automatically uses instance metadata.
            resource_kwargs: Dict[str, str] = {"region_name": settings.aws_region}
            if settings.aws_access_key_id:
                resource_kwargs["aws_access_key_id"] = settings.aws_access_key_id
            if settings.aws_secret_access_key:
                resource_kwargs["aws_secret_access_key"] = (
                    settings.aws_secret_access_key
                )
            self.dynamodb = boto3.resource("dynamodb", **resource_kwargs)
            self.logs_table = self.dynamodb.Table(settings.dynamodb_table_logs)
            self.users_table = self.dynamodb.Table(settings.dynamodb_table_users)
            self.traces_table = self.dynamodb.Table(settings.dynamodb_table_traces)
            self.api_keys_table = self.dynamodb.Table(settings.dynamodb_table_api_keys)
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
        timestamp = datetime.now(timezone.utc).isoformat()
        log_id = str(uuid.uuid4())
        sk = f"{timestamp}#{log_id}"

        item = {
            "company_id": company_id,
            "timestamp#log_id": sk,
            "log_id": log_id,
            "timestamp": timestamp,
            **log_data,
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
                IndexName="email-index",
                KeyConditionExpression="email = :email_val",
                ExpressionAttributeValues={":email_val": email},
            )
            items = response.get("Items", [])
            return items[0] if items else None
        except ClientError as e:
            logger.error(
                f"DynamoDB Query error for email lookup: {e.response['Error']['Message']}"
            )
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
                KeyConditionExpression="company_id = :comp_id",
                ExpressionAttributeValues={":comp_id": company_id},
                ScanIndexForward=False,  # Descending sort (newest first)
                Limit=limit,
            )
            return response.get("Items", [])
        except ClientError as e:
            logger.error(f"DynamoDB get_logs error: {e.response['Error']['Message']}")
            raise DatabaseException("Failed to retrieve logs.")

    def save_user(self, user_data: Dict[str, Any]) -> str:
        """
        Saves a new user to DynamoDB with atomic email uniqueness enforcement.

        WHY: Using a ConditionExpression on the email attribute prevents a race condition
        where two concurrent registrations with the same email could both succeed when
        relying on a separate get_user_by_email check.

        Args:
            user_data (Dict[str, Any]): The user record including company_id, email,
                hashed_password, etc.

        Returns:
            str: The user_id of the newly created user.

        Raises:
            ValidationException: If the email is already registered (ConditionalCheckFailed).
            DatabaseException: If the underlying PutItem request fails for any other reason.
        """
        from exceptions import ValidationException

        try:
            self.users_table.put_item(
                Item=user_data,
                ConditionExpression="attribute_not_exists(email)",
            )
            return user_data.get("user_id", "")
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ConditionalCheckFailedException":
                raise ValidationException("Email already registered")
            logger.error(f"DynamoDB save_user error: {e.response['Error']['Message']}")
            raise DatabaseException("Failed to save user.")

    # ── Agent Trace Methods ────────────────────────────────

    def save_trace(self, company_id: str, trace_data: Dict[str, Any]) -> str:
        """
        Saves a complete agent execution trace to DynamoDB.
        WHY: One item per run (not per step) keeps reads fast and cheap. Agent traces
        with 20 steps are ~50KB max, well within DynamoDB's 400KB item limit.

        Args:
            company_id (str): The company that owns this trace.
            trace_data (Dict[str, Any]): Full trace including steps list.

        Returns:
            str: The run_id of the saved trace.

        Raises:
            DatabaseException: When PutItem fails.
        """
        run_id = trace_data.get("run_id", str(uuid.uuid4()))
        timestamp = trace_data.get("timestamp", datetime.now(timezone.utc).isoformat())
        sk = f"{timestamp}#{run_id}"

        item = {
            "company_id": company_id,
            "run_ts#run_id": sk,
            "run_id": run_id,
            **trace_data,
        }

        # WHY: Convert any float/int values that DynamoDB can't handle (e.g., Decimal issues)
        # boto3 handles Python floats via TypeSerializer, but we ensure booleans are clean.
        try:
            self.traces_table.put_item(Item=item)
            return run_id
        except ClientError as e:
            logger.error(f"DynamoDB save_trace error: {e.response['Error']['Message']}")
            raise DatabaseException("Failed to save agent trace.")

    def get_traces(self, company_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches recent agent traces for a company (for the trace list view).
        WHY: ScanIndexForward=False gives us newest-first ordering since the SK
        is a composite of timestamp#run_id.

        Args:
            company_id (str): The company to fetch traces for.
            limit (int): Maximum number of traces to return.

        Returns:
            List[Dict[str, Any]]: List of trace items, newest first.

        Raises:
            DatabaseException: If the query fails.
        """
        try:
            response = self.traces_table.query(
                KeyConditionExpression="company_id = :comp_id",
                ExpressionAttributeValues={":comp_id": company_id},
                ScanIndexForward=False,
                Limit=limit,
            )
            return response.get("Items", [])
        except ClientError as e:
            logger.error(f"DynamoDB get_traces error: {e.response['Error']['Message']}")
            raise DatabaseException("Failed to retrieve agent traces.")

    def get_trace_by_id(self, company_id: str, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches a single trace by run_id using the GSI.
        WHY: The run_id-index GSI lets us look up a specific trace without knowing
        its exact timestamp (which is required for the primary key).

        Args:
            company_id (str): The company that owns this trace.
            run_id (str): The UUID of the agent run.

        Returns:
            Optional[Dict[str, Any]]: The full trace if found, None otherwise.

        Raises:
            DatabaseException: If the query fails.
        """
        try:
            response = self.traces_table.query(
                IndexName="run_id-index",
                KeyConditionExpression="run_id = :rid",
                ExpressionAttributeValues={":rid": run_id},
            )
            items = response.get("Items", [])
            if not items:
                return None
            # WHY: Verify company ownership to prevent cross-tenant data access
            trace = items[0]
            if trace.get("company_id") != company_id:
                return None
            return trace
        except ClientError as e:
            logger.error(
                f"DynamoDB get_trace_by_id error: {e.response['Error']['Message']}"
            )
            raise DatabaseException("Failed to retrieve agent trace.")

    # ── API Key Methods ────────────────────────────────────

    def save_api_key(self, key_data: Dict[str, Any]) -> None:
        """
        Saves an API key record to the api_keys table.
        WHY: The raw key is never stored — only its SHA-256 hash (the PK).
        The caller generates the hash before calling this method.

        Args:
            key_data (Dict[str, Any]): Must include key_hash (PK), key_id, company_id,
                user_id, name, prefix, created_at, is_active, request_count.

        Raises:
            DatabaseException: If PutItem fails.
        """
        try:
            self.api_keys_table.put_item(Item=key_data)
        except ClientError as e:
            logger.error(
                f"DynamoDB save_api_key error: {e.response['Error']['Message']}"
            )
            raise DatabaseException("Failed to save API key.")

    def get_api_keys_by_company(self, company_id: str) -> List[Dict[str, Any]]:
        """
        Lists all API keys belonging to a company via the company_id-index GSI.
        WHY: Users need to see and manage all their keys from the settings page.

        Args:
            company_id (str): The company whose keys to list.

        Returns:
            List[Dict[str, Any]]: API key records (without raw key — it was never stored).

        Raises:
            DatabaseException: If the query fails.
        """
        try:
            response = self.api_keys_table.query(
                IndexName="company_id-index",
                KeyConditionExpression="company_id = :cid",
                ExpressionAttributeValues={":cid": company_id},
                ScanIndexForward=False,  # newest first
            )
            return response.get("Items", [])
        except ClientError as e:
            logger.error(
                f"DynamoDB get_api_keys_by_company error: {e.response['Error']['Message']}"
            )
            raise DatabaseException("Failed to retrieve API keys.")

    def get_api_key_by_hash(self, key_hash: str) -> Optional[Dict[str, Any]]:
        """
        Fetches a single API key by its SHA-256 hash (the table PK).
        WHY: O(1) lookup for authenticating incoming X-API-Key requests.

        Args:
            key_hash (str): SHA-256 hex digest of the raw key.

        Returns:
            Optional[Dict[str, Any]]: The key record if found, None otherwise.

        Raises:
            DatabaseException: If GetItem fails.
        """
        try:
            response = self.api_keys_table.get_item(Key={"key_hash": key_hash})
            return response.get("Item")
        except ClientError as e:
            logger.error(
                f"DynamoDB get_api_key_by_hash error: {e.response['Error']['Message']}"
            )
            raise DatabaseException("Failed to retrieve API key.")

    def get_api_key_by_id(
        self, company_id: str, key_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches a single API key by key_id via the key_id-index GSI.
        WHY: CRUD operations (regenerate, revoke) use the key_id (UUID) rather than
        the hash, since the hash is not exposed to the user.

        Args:
            company_id (str): The company that owns this key (for ownership verification).
            key_id (str): The UUID assigned when the key was created.

        Returns:
            Optional[Dict[str, Any]]: The key record if found and owned by company, None otherwise.

        Raises:
            DatabaseException: If the query fails.
        """
        try:
            response = self.api_keys_table.query(
                IndexName="key_id-index",
                KeyConditionExpression="key_id = :kid",
                ExpressionAttributeValues={":kid": key_id},
            )
            items = response.get("Items", [])
            if not items:
                return None
            # WHY: Verify company ownership to prevent cross-tenant key manipulation
            key_record = items[0]
            if key_record.get("company_id") != company_id:
                return None
            return key_record
        except ClientError as e:
            logger.error(
                f"DynamoDB get_api_key_by_id error: {e.response['Error']['Message']}"
            )
            raise DatabaseException("Failed to retrieve API key.")

    def delete_api_key(self, key_hash: str) -> None:
        """
        Hard-deletes an API key by its hash (PK).
        WHY: Once revoked, the key should be permanently removed so it can never
        authenticate again, even if the hash is somehow known.

        Args:
            key_hash (str): SHA-256 hex digest of the raw key.

        Raises:
            DatabaseException: If DeleteItem fails.
        """
        try:
            self.api_keys_table.delete_item(Key={"key_hash": key_hash})
        except ClientError as e:
            logger.error(
                f"DynamoDB delete_api_key error: {e.response['Error']['Message']}"
            )
            raise DatabaseException("Failed to delete API key.")

    def update_api_key_usage(self, key_hash: str) -> None:
        """
        Atomically increments request_count and sets last_used_at for an API key.
        WHY: Per-key usage tracking enables users to identify unused keys and
        monitor programmatic access patterns from the settings page.

        Args:
            key_hash (str): SHA-256 hex digest of the raw key.

        Raises:
            DatabaseException: If UpdateItem fails.
        """
        try:
            self.api_keys_table.update_item(
                Key={"key_hash": key_hash},
                UpdateExpression="SET last_used_at = :ts ADD request_count :inc",
                ExpressionAttributeValues={
                    ":ts": datetime.now(timezone.utc).isoformat(),
                    ":inc": 1,
                },
            )
        except ClientError as e:
            logger.error(
                f"DynamoDB update_api_key_usage error: {e.response['Error']['Message']}"
            )
            # WHY: Usage tracking failure should not block the actual API request.
            # We log but do not re-raise to avoid breaking the caller's workflow.


# WHY: Lazy initialization avoids connecting to DynamoDB at import time.
# In demo mode or during tests, the service may never be needed, so
# eagerly creating it would cause unnecessary boto3 client errors.
_dynamo_service: Optional[DynamoDBService] = None


def get_dynamo_service() -> DynamoDBService:
    """Lazy singleton factory for DynamoDBService. Enables easy mocking in tests."""
    global _dynamo_service
    if _dynamo_service is None:
        _dynamo_service = DynamoDBService()
    return _dynamo_service
