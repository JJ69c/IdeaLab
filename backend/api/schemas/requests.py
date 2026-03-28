from pydantic import BaseModel, Field, model_validator


class IdeaInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Short name for the idea")
    description: str = Field(..., min_length=10, description="Detailed description of the idea")
    category: str = Field(
        default="general",
        description="Product category (e.g. saas, mobile_app, marketplace, fintech, health, custom)",
    )
    stage: str = Field(
        default="concept",
        description="Idea maturity: concept, prototype, mvp, launched",
    )
    target_audience: str = Field(default="general public", description="Who this is for")
    problem_statement: str = Field(default="", description="The problem this idea solves")
    price_point: str = Field(default="not specified", description="Pricing model or price")
    existing_alternatives: str = Field(default="", description="Known competitors or alternatives")
    differentiator: str = Field(default="", description="Key differentiator from alternatives")
    known_strengths: str = Field(default="", description="Strengths the founder already knows about")
    known_risks: str = Field(default="", description="Risks or concerns the founder is aware of")


class SimulationConfigInput(BaseModel):
    num_ticks: int = Field(default=8, ge=3, le=20, description="Number of simulation rounds")
    population_size: int = Field(default=30, ge=10, le=50, description="Number of NPCs")
    seed_count: int = Field(default=8, ge=1, le=15, description="NPCs initially exposed")

    @model_validator(mode="after")
    def seed_within_population(self) -> "SimulationConfigInput":
        if self.seed_count > self.population_size:
            raise ValueError(
                f"seed_count ({self.seed_count}) cannot exceed "
                f"population_size ({self.population_size})"
            )
        return self


class AssetReference(BaseModel):
    asset_id: str | None = Field(
        default=None,
        description="ID returned by the upload endpoint (None for URL-only assets)",
    )
    asset_type: str = Field(
        ...,
        description="Asset type: website, app_ui, product_photo, packaging, prototype, marketing_visual",
    )
    url: str | None = Field(default=None, description="Original URL if this is a website")
    note: str = Field(default="", max_length=200, description="What this asset represents")


class AskNpcRequest(BaseModel):
    npc_id: str = Field(..., description="ID of the NPC to ask")
    question: str = Field(..., min_length=1, max_length=500, description="Question to ask the NPC")


class CreateSimulationRequest(BaseModel):
    idea: IdeaInput
    config: SimulationConfigInput = SimulationConfigInput()
    asset_refs: list[AssetReference] = Field(default_factory=list, max_length=5)
    parent_simulation_id: str | None = Field(
        default=None, description="ID of the parent simulation (for variants)"
    )
    variant_name: str | None = Field(
        default=None, max_length=200, description="Label for this variant (e.g. 'Lower price test')"
    )
    use_parent_seeds: bool = Field(
        default=False,
        description=(
            "If True, the variant uses the same initial seed NPCs as the parent "
            "(same 8 people exposed first), giving a controlled A/B comparison. "
            "If False, seeds are re-selected via stratified sampling (different first-exposure). "
            "Ignored when parent_simulation_id is not set."
        ),
    )
