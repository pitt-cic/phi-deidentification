#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { PiiDeidentificationStack } from '../lib/pii-deidentification-stack';

const app = new cdk.App();
new PiiDeidentificationStack(app, 'PiiDeidentificationStack');

cdk.Tags.of(app).add('Project', 'PII Deidentification');
cdk.Tags.of(app).add('Purpose', process.env.PURPOSE || 'Demo');
cdk.Tags.of(app).add('Owner', process.env.OWNER_NAME || 'CDK');
