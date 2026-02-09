#!/usr/bin/env python3
import aws_cdk as cdk
from pii_deidentification_stack import PiiDeidentificationStack

app = cdk.App()
PiiDeidentificationStack(app, "PiiDeidentificationStack")
app.synth()
