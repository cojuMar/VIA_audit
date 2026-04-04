from pydantic import BaseModel


class IntegrationCreate(BaseModel):
    connector_key: str
    integration_name: str
    auth_config: dict = {}
    field_mappings: dict = {}
    sync_schedule: str = "0 */6 * * *"


class IntegrationUpdate(BaseModel):
    integration_name: str | None = None
    auth_config: dict | None = None
    field_mappings: dict | None = None
    sync_schedule: str | None = None
    status: str | None = None


class OAuthTokenCreate(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None  # seconds from now
    scope: str | None = None


class WebhookPayload(BaseModel):
    event_type: str
    source_event_id: str | None = None
    payload: dict


class FieldMappingUpdate(BaseModel):
    data_type: str
    mappings: list[dict]  # [{source_field, target_field, transform_fn, is_required}]
    auto_populate_from_template: bool = True


class SyncRequest(BaseModel):
    data_types: list[str] | None = None  # None = sync all supported
    sync_type: str = "manual"
