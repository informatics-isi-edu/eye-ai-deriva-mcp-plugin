"""MCP prompt registrations for the eye-ai plugin.

Prompts are pre-built conversation starters surfaced by MCP clients.
Each returns a string that primes the LLM for a specific eye-ai research
workflow over the catalog's clinical domain tables.

These are eye-ai DOMAIN prompts. They deliberately do not duplicate the
co-loaded deriva-ml-mcp-plugin's prompts (``deriva_ml_concepts`` /
``deriva_ml_getting_started``), which cover the ML-domain layer (Dataset
/ Workflow / Execution / Feature / Asset), nor deriva-mcp-core's generic
catalog prompts. They cover what neither does: the ophthalmology /
retinal-imaging domain -- subjects, encounters (Observation), fundus/OCT
images, and the diagnosis vocabularies that link them.

This plugin ships no domain query tools, so the prompts steer the LLM to
``rag_search`` (eye-ai rows are RAG-indexed by this plugin; vocabularies
and datasets by the sibling) and to the generic ``deriva-mcp-core``
query tools (``get_entities``, ``query_attribute``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deriva_mcp_core.plugin.api import PluginContext

# Default catalog coordinates. ``eye-ai`` is the catalog alias (it
# resolves to the numeric catalog server-side); both forms work as a
# catalog_id.
_DEFAULT_HOSTNAME = "www.eye-ai.org"
_DEFAULT_CATALOG_ID = "eye-ai"


def register(ctx: PluginContext, hostname: str = _DEFAULT_HOSTNAME) -> None:
    """Register the eye-ai domain MCP prompts on ``ctx``.

    Args:
        ctx: PluginContext supplied by deriva-mcp-core at startup.
        hostname: Default eye-ai hostname baked into each prompt's
            ``hostname`` argument default.

    Returns:
        None.

    Example:
        >>> from deriva_mcp_core.plugin.api import PluginContext
        >>> # ctx provided by the framework
        >>> register(ctx)  # doctest: +SKIP
    """

    @ctx.prompt(name="eye-ai-assistant")
    def eye_ai_assistant(hostname: str = hostname, catalog_id: str = _DEFAULT_CATALOG_ID) -> str:
        return (
            f"You are an ophthalmology research assistant with access to the Eye-AI data "
            f"catalog at {hostname} (catalog {catalog_id}). Eye-AI is a data resource for "
            f"ophthalmic and retinal-imaging research, containing subjects, clinical "
            f"encounters, fundus and OCT images, and diagnosis labels for conditions such as "
            f"glaucoma and diabetic retinopathy.\n\n"
            f"You can help researchers:\n"
            f" * Find images by diagnosis, imaging modality, laterality, or field angle\n"
            f" * Explore a subject's clinical encounters (Observation) and demographics\n"
            f" * Trace which subjects, encounters, and images carry a given diagnosis\n"
            f" * Navigate the diagnosis and imaging controlled vocabularies\n\n"
            f"The catalog's clinical domain rows (Subject, Image, Observation) and its "
            f"vocabularies are indexed for semantic search -- use the rag_search tool to find "
            f"relevant records, and the generic deriva-mcp-core query tools (get_entities, "
            f"query_attribute) to retrieve structured detail. Always include record RIDs in "
            f"your responses so researchers can locate records directly.\n\n"
            f"ADDITIONAL INSTRUCTIONS:\n"
            f"1. Answer questions using PRIMARILY the provided Eye-AI context, but it is "
            f"acceptable to fall back on your own knowledge for a more general but related "
            f"clinical topic.\n"
            f"2. For technical/medical terms, provide clear definitions from the context.\n"
            f"3. Organize information logically with proper structure.\n"
            f"4. If the context has partial information, synthesize what's available.\n"
            f"5. Be specific -- include RIDs and identifiers when mentioned.\n"
            f"6. If information is insufficient, clearly state what's missing.\n"
            f"7. Cite sources naturally (e.g., 'According to Subject 1-ABCD...').\n\n"
            f"CONTEXT USAGE:\n"
            f"- Prioritize sources with higher relevance scores.\n"
            f"- Cross-reference multiple sources when they discuss the same subject or image.\n"
            f"- Extract specific facts: diagnoses, imaging modality, laterality, demographics.\n"
            f"- Include relevant clinical details and identifiers."
        )

    @ctx.prompt(name="find-images")
    def find_images(
        criteria: str,
        hostname: str = hostname,
        catalog_id: str = _DEFAULT_CATALOG_ID,
    ) -> str:
        return (
            f"Search the Eye-AI catalog at {hostname} (catalog {catalog_id}) for images "
            f"matching: {criteria}\n\n"
            f"Steps to follow:\n"
            f"1. Use rag_search to find semantically relevant Image rows (and the Observation "
            f"   / Subject rows they hang off) matching the criteria.\n"
            f"2. Use get_entities or query_attribute on eye-ai:Image to retrieve structured "
            f"   metadata for the most promising candidates (Image_Side, Image_Angle, "
            f"   Image_Modality, Observation).\n"
            f"3. For each relevant image, report: RID, laterality (Image_Side), field angle "
            f"   (Image_Angle), modality, the linked encounter (Observation), and any diagnosis "
            f"   from the eye-ai:Image_Diagnosis association.\n"
            f"4. IMPORTANT: If the criteria name a specific diagnosis, modality, laterality, or "
            f"   angle, resolve it against the corresponding vocabulary first "
            f"   (eye-ai:Diagnosis_Image, eye-ai:Modality_Type, eye-ai:Image_Side, "
            f"   eye-ai:Image_Angle) via query_attribute to find the exact controlled term. "
            f"   Only fall back to regex matching if no exact term is found.\n\n"
            f"Present results as a ranked list with the most relevant images first."
        )

    @ctx.prompt(name="explore-diagnosis")
    def explore_diagnosis(
        diagnosis: str,
        hostname: str = hostname,
        catalog_id: str = _DEFAULT_CATALOG_ID,
    ) -> str:
        return (
            f"Explore Eye-AI records at {hostname} (catalog {catalog_id}) that carry the "
            f"diagnosis: {diagnosis}\n\n"
            f"Steps to follow:\n"
            f"1. Resolve '{diagnosis}' to a canonical term in the diagnosis vocabularies "
            f"   (eye-ai:Diagnosis_Image for image-level findings; eye-ai:Diagnosis_Subject "
            f"   and eye-ai:Diagnosis_Observation for subject- and encounter-level), checking "
            f"   Name and Synonyms.\n"
            f"2. Use the matched term to traverse the association tables -- "
            f"   eye-ai:Image_Diagnosis (-> Image), eye-ai:Subject_Diagnosis (-> Subject), and "
            f"   eye-ai:Observation_Diagnosis (-> Observation) -- to find the linked records.\n"
            f"3. For each record found, retrieve its identifying detail: for images the "
            f"   modality / laterality / angle and the parent encounter; for subjects the "
            f"   demographics; for observations the encounter findings.\n"
            f"4. Summarize how the diagnosis is distributed across subjects, encounters, and "
            f"   images, and note the imaging modalities involved.\n\n"
            f"If no exact diagnosis match is found, suggest the closest available terms from "
            f"the diagnosis vocabularies."
        )
