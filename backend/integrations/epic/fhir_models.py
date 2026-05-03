from importlib import import_module
from typing import Any


FHIR_PACKAGE_PREFIXES = ("fhir.resources.R4B", "fhir.resources")


def parse_fhir_resource(resource: dict[str, Any]) -> Any:
    resource_type = resource.get("resourceType")
    if not resource_type:
        raise ValueError("FHIR resource is missing resourceType")

    last_error: Exception | None = None
    for package_prefix in FHIR_PACKAGE_PREFIXES:
        try:
            module = import_module(f"{package_prefix}.{resource_type.lower()}")
            model_class = getattr(module, resource_type)
            return model_class.model_validate(resource)
        except (AttributeError, ModuleNotFoundError, ValueError) as exc:
            last_error = exc

    raise ValueError(f"Unsupported FHIR resourceType: {resource_type}") from last_error


def parse_fhir_resources(resources: list[dict[str, Any]]) -> list[Any]:
    return [parse_fhir_resource(resource) for resource in resources]
