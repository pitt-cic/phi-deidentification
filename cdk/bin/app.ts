#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { PiiDeidentificationStack } from '../lib/pii-deidentification-stack';

const app = new cdk.App();
new PiiDeidentificationStack(app, 'PiiDeidentificationStack');
