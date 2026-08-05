#!/usr/bin/env python3
"""CDK App entry point for Travel Insurance RAG Chat Backend.

Usage:
  cdk synth                          # Synthesize CloudFormation template
  cdk deploy                          # Deploy the dev stack
  cdk deploy -c env=prod             # Deploy a prod stack
  cdk deploy -c enable_alb=true      # Deploy with ALB enabled
"""

from aws_cdk import App, Environment

from travel_insurance_stack import TravelInsuranceStack

app = App()

# Resolve context variables with defaults
env_name = app.node.try_get_context("env") or "dev"
enable_alb = app.node.try_get_context("enable_alb") == "true"

TravelInsuranceStack(
    app,
    f"TravelInsurance-{env_name}",
    env_name=env_name,
    enable_load_balancer=enable_alb,
    env=Environment(
        account=app.node.try_get_context("account") or None,
        region=app.node.try_get_context("region") or "us-east-1",
    ),
    description=f"Travel Insurance RAG Backend — {env_name} environment",
)

app.synth()
