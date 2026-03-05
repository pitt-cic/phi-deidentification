#!/usr/bin/env node
/**
 * CDK application entry point for PHI Deidentification Platform.
 * Defines infrastructure stack and applies project tags.
 */
import * as cdk from 'aws-cdk-lib';
import { PiiDeidentificationStack } from '../lib/phi-deidentification-stack';

const app = new cdk.App();
new PiiDeidentificationStack(app, 'PHIDeidentificationStack');

cdk.Tags.of(app).add('Project', 'PHI Deidentification');
cdk.Tags.of(app).add('Purpose', process.env.PURPOSE || 'Demo');
cdk.Tags.of(app).add('Owner', process.env.OWNER_NAME || 'CDK');
