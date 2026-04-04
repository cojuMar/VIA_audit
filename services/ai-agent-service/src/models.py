from pydantic import BaseModel


class ChatRequest(BaseModel):
    conversation_id: str | None = None  # None = new conversation
    message: str
    user_identifier: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    content: str
    tool_calls_made: list[str]  # names of tools called
    input_tokens: int
    output_tokens: int
    latency_ms: int


class ReportRequest(BaseModel):
    report_type: str
    title: str | None = None
    natural_language_request: str
    conversation_id: str | None = None


class ScheduledQueryCreate(BaseModel):
    query_name: str
    natural_language_query: str
    schedule_cron: str = "0 9 * * 1"
    delivery_config: dict = {}


class ScheduledQueryUpdate(BaseModel):
    query_name: str | None = None
    natural_language_query: str | None = None
    schedule_cron: str | None = None
    delivery_config: dict | None = None


class FeedbackCreate(BaseModel):
    message_id: str
    conversation_id: str
    rating: int  # 1-5
    feedback_type: str | None = None
    comment: str | None = None


class ConversationTitleUpdate(BaseModel):
    title: str
