"""Pydantic request/response schemas for the HTTP API.

Domain objects (robots, orders, roads, nodes) live with their behaviour in ``agents`` and
``simulation``; persisted forms live in ``app.db.tables``. These models define the API
contract only.
"""
