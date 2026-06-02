"""drf-spectacular extensions so the generated TypeScript types are precise."""

from drf_spectacular.extensions import (
    OpenApiAuthenticationExtension,
    OpenApiSerializerFieldExtension,
)
from drf_spectacular.plumbing import build_basic_type
from drf_spectacular.types import OpenApiTypes


class SessionAuthScheme(OpenApiAuthenticationExtension):
    target_class = "apps.core.authentication.SessionAuthentication"
    name = "sessionAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": "sessionid"}


class StaffUserFieldExtension(OpenApiSerializerFieldExtension):
    target_class = "apps.core.api.StaffUserField"

    def map_serializer_field(self, auto_schema, direction):
        schema = build_basic_type(OpenApiTypes.UUID)
        schema["nullable"] = True
        return schema


class TenantRelatedFieldExtension(OpenApiSerializerFieldExtension):
    target_class = "apps.core.api.TenantRelatedField"

    def map_serializer_field(self, auto_schema, direction):
        return build_basic_type(OpenApiTypes.UUID)
