"""
Module: mlflow_service.py
Purpose: Logs metrics and artifacts about LLM usage to the MLFlow tracking server.
WHY: Using a standardized tracking server like MLFlow allows the MLOps team to evaluate
models efficiently and build fine-tuning datasets later independent of standard application DB logs.
"""

import mlflow
from typing import Optional, Dict, Any
from config import settings, logger


class MLFlowService:
    """Service to asynchronously interact with MLFlow."""

    def __init__(self):
        # WHY: Setting tracking URI centrally ensures all runs go to the right instance
        try:
            mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
            logger.info(f"MLFlow tracking URI set to {settings.mlflow_tracking_uri}")
        except Exception as e:
            logger.error(f"Failed to set MLFlow tracking URI: {str(e)}")

    def log_llm_call(
        self,
        company_id: str,
        model_name: str,
        thinking_mode: bool,
        prompt_length: int,
        latency_ms: float,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        success: bool,
        prompt_preview: str,
        response_preview: str,
        error_type: Optional[str] = None,
    ) -> None:
        """
        Records an individual LLM generation run in MLFlow.

        Args:
            company_id (str): Tenant identifier to group experiments.
            model_name (str): Identifier of the LLM used.
            thinking_mode (bool): Whether reasoning mode was active.
            prompt_length (int): Character length of the prompt.
            latency_ms (float): Request duration in milliseconds.
            input_tokens (int): Tokenization count of prompt.
            output_tokens (int): Tokenization count of response.
            cost_usd (float): Estimated operational or API cost.
            success (bool): Whether the request returned 200 OK.
            prompt_preview (str): Masked prompt.
            response_preview (str): Masked response.
            error_type (Optional[str]): Exception class string if failed.
        """
        # WHY: Company-specific experiments simplify data partitioning for analytics
        experiment_name = f"llmwatch_{company_id}"
        try:
            mlflow.set_experiment(experiment_name)

            with mlflow.start_run(run_name=f"{model_name}-inference"):
                # Params
                mlflow.log_params(
                    {
                        "model_name": model_name,
                        "company_id": company_id,
                        "prompt_length": prompt_length,
                        "thinking_mode": thinking_mode,
                    }
                )

                # Metrics
                mlflow.log_metrics(
                    {
                        "latency_ms": latency_ms,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cost_usd": cost_usd,
                        "success": 1.0 if success else 0.0,
                    }
                )

                # Artifacts (as tags since they are text fragments)
                # WHY: Real MLFlow artifacts write files, which is too slow for real-time.
                # Tags are highly searchable string metadata.
                mlflow.log_tags(
                    {
                        "prompt_preview": prompt_preview,
                        "response_preview": response_preview,
                        "error_type": error_type or "none",
                    }
                )

        except Exception as e:
            # WHY: MLFlow logging failure shouldn't abort the client response, so we just log locally
            logger.error(f"Failed to log to MLFlow: {str(e)}")


mlflow_service = MLFlowService()


def get_mlflow_service() -> MLFlowService:
    """Lazy factory for MLFlowService. Enables easy mocking in tests."""
    return mlflow_service
