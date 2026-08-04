"""API router assembly."""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    routes_compare,
    routes_dossiers,
    routes_graph,
    routes_import,
    routes_intelligence,
    routes_knowledge,
    routes_search,
    routes_sources,
    routes_system,
)

api_router = APIRouter()
api_router.include_router(routes_system.router)
api_router.include_router(routes_import.router)
api_router.include_router(routes_sources.router)
api_router.include_router(routes_knowledge.router)
api_router.include_router(routes_knowledge.promote_router)
api_router.include_router(routes_graph.entities_router)
api_router.include_router(routes_graph.tags_router)
api_router.include_router(routes_graph.links_router)
api_router.include_router(routes_graph.collections_router)
api_router.include_router(routes_dossiers.router)
api_router.include_router(routes_compare.router)
api_router.include_router(routes_search.router)
api_router.include_router(routes_intelligence.router)

__all__ = ["api_router"]
