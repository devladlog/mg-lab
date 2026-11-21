"""connectorkit: check a custom connector's files and run them the way the platform is documented to.

- definition: OpenAPI 2.0 schema check, Learn's connector rules, webhook trigger rules, connection parameters
- runtime:    builds the HTTP request for an operation (path and query parameters, defaults, policy templates,
              basic authentication), and subscribes and unsubscribes webhook triggers
"""
from .definition import Finding, Connector, load_connector, validate
from .runtime import Connection, Request, Response, Runtime

__all__ = ["Finding", "Connector", "load_connector", "validate", "Connection", "Request", "Response", "Runtime"]
