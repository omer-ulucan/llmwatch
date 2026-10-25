"""
Module: workspaces.py
Purpose: Endpoints for the caller's workspace (view, delete).
WHY: Deleting a workspace removes every user, key, log, trace and eval it owns, so
it is restricted to the owner, requires a browser session (not an API key) and a
typed confirmation of the workspace name.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.dependencies import get_current_user, require_owner
from llmwatch.config import logger
from llmwatch.db.engine import get_session
from llmwatch.db.models import Workspace
from llmwatch.exceptions import ResourceNotFoundException, ValidationException
from llmwatch.models.schemas import DeleteWorkspaceRequest, WorkspaceInfo
from llmwatch.rate_limit import limiter

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


async def _load(session: AsyncSession, workspace_id: str) -> Workspace:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise ResourceNotFoundException("Workspace not found")
    return workspace


@router.get("/current", response_model=WorkspaceInfo)
async def get_current_workspace(
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await _load(session, current_user["workspace_id"])


@router.delete("/current", status_code=204)
@limiter.limit("5/minute")
async def delete_current_workspace(
    request: Request,
    body: DeleteWorkspaceRequest,
    current_user: Dict[str, Any] = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    """
    Permanently deletes the workspace and everything in it (cascades in the DB).
    """
    workspace = await _load(session, current_user["workspace_id"])
    if body.confirm_name.strip() != workspace.name:
        raise ValidationException("confirm_name does not match the workspace name")

    await session.execute(delete(Workspace).where(Workspace.id == workspace.id))
    await session.commit()
    logger.warning(
        f"Workspace deleted: id={workspace.id} by user={current_user['user_id']}"
    )
    return Response(status_code=204)
