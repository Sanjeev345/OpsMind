from pydantic import BaseModel, Field, model_validator


class FeedbackRequest(BaseModel):
    incident_id: str = Field(min_length=1, max_length=32)
    correct: bool
    actual_root_cause: str = Field(default="", max_length=500)
    actual_resolution: str = Field(default="", max_length=1000)
    engineer_note: str = Field(default="", max_length=1500)

    @model_validator(mode="after")
    def _validate(self):
        self.actual_root_cause = self.actual_root_cause.strip()
        self.actual_resolution = self.actual_resolution.strip()
        self.engineer_note = self.engineer_note.strip()
        if not self.correct and not self.actual_root_cause:
            raise ValueError("actual_root_cause is required when the diagnosis is marked incorrect")
        if not (self.actual_root_cause or self.actual_resolution or self.engineer_note):
            raise ValueError("Provide at least a root cause, resolution or engineer note to teach OpsMind")
        return self


class RetainedMemory(BaseModel):
    document_id: str
    memory_type: str
    content: str


class FeedbackResponse(BaseModel):
    stored: bool
    incident_id: str
    bank_id: str
    retained: list[RetainedMemory]
    lesson: str
    lesson_generated_by: str
    stored_at: str
    memory_stats: dict | None = None
