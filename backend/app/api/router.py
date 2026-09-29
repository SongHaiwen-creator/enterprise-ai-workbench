from fastapi import APIRouter

from app.api.routes.agents import router as agents_router
from app.api.routes.answers import router as answers_router
from app.api.routes.approvals import router as approvals_router
from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.execution_logs import router as execution_logs_router
from app.api.routes.knowledge_bases import router as knowledge_bases_router
from app.api.routes.retrieval import router as retrieval_router
from app.api.routes.tools import assignment_router as agent_tools_router
from app.api.routes.tools import router as tools_router
from app.api.routes.workspaces import router as workspaces_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(workspaces_router)
api_router.include_router(knowledge_bases_router)
api_router.include_router(documents_router)
api_router.include_router(retrieval_router)
api_router.include_router(answers_router)
api_router.include_router(agents_router)
api_router.include_router(tools_router)
api_router.include_router(agent_tools_router)
api_router.include_router(approvals_router)
api_router.include_router(execution_logs_router)
