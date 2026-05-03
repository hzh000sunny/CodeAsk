"""Aggregate router for wiki-related endpoints."""

from fastapi import APIRouter

from codeask.api.documents_compat import router as documents_router
from codeask.api.features import router as features_router
from codeask.api.reports import router as reports_router
from codeask.api.wiki.assets import router as wiki_assets_router
from codeask.api.wiki.documents import router as wiki_documents_router
from codeask.api.wiki.drafts import router as wiki_drafts_router
from codeask.api.wiki.imports import router as wiki_imports_router
from codeask.api.wiki.nodes import router as nodes_router
from codeask.api.wiki.spaces import router as spaces_router
from codeask.api.wiki.tree import router as tree_router
from codeask.api.wiki.versions import router as wiki_versions_router

router = APIRouter()
router.include_router(features_router)
router.include_router(documents_router)
router.include_router(reports_router)
router.include_router(spaces_router, prefix="/wiki/spaces")
router.include_router(tree_router, prefix="/wiki")
router.include_router(nodes_router, prefix="/wiki")
router.include_router(wiki_documents_router, prefix="/wiki")
router.include_router(wiki_drafts_router, prefix="/wiki")
router.include_router(wiki_versions_router, prefix="/wiki")
router.include_router(wiki_assets_router, prefix="/wiki")
router.include_router(wiki_imports_router, prefix="/wiki")
