"""Shared Powertools Logger for API Lambda."""
from aws_lambda_powertools import Logger

logger = Logger(service="phi_deidentification.api")
