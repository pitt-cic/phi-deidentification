# PHI Deidentification Platform

| Index                         | Description                                                   |
|:------------------------------|:--------------------------------------------------------------|
| [Overview](#overview)         | See what this project does and its key capabilities           |
| [Demo](#demo)                 | View the demo experience and walkthrough video                |
| [Description](#description)   | Learn about the problem and our approach                      |
| [Architecture](#architecture) | View the system architecture diagram                          |
| [Tech Stack](#tech-stack)     | Technologies and services used                                |
| [Deployment](#deployment)     | How to install and deploy the solution                        |
| [Usage](#usage)               | How to process notes and approve redactions                   |
| [Costs](#costs)               | Cost drivers and estimation guidance                          |
| [Credits](#credits)           | Project ownership and contributors                            |
| [License](#license)           | Current license status for this repository                    |
| [Disclaimers](#disclaimers)   | Important legal and operational disclaimers                   |

# Overview

PHI Deidentification Platform is an AI-driven system for detecting and redacting sensitive information in clinical and operational text documents. The solution uses large language models (LLMs) through AWS services to identify PHI with context awareness, generate redacted outputs, and support human review before release.

A University of Pittsburgh research team requested this project to address challenges with existing deidentification approaches: static PHI identifier lists that miss context-specific or unique information, long processing times for large note volumes, and mid-processing failures that require full restarts.

The platform provides end-to-end capabilities including batch ingestion, asynchronous processing, LLM-based detection,
redacted artifact generation, reviewer approval workflows, and operational metrics for monitoring system health.

Key capabilities include:

- **Automated PHI Detection**: Uses Claude via Amazon Bedrock to identify sensitive entities in clinical or operational notes.
- **Redacted Output Generation**: Produces redacted text and entity metadata for each input note.
- **Human-in-the-Loop Review**: Provides a dashboard to compare original vs redacted text, edit, and approve.
- **Async Processing at Scale**: Uses S3, SQS, and Lambda for asynchronous, serverless processing.
- **Operational Visibility**: Tracks batch stats and emits CloudWatch metrics for throughput, latency, retries, and failures.

# Demo

https://github.com/user-attachments/assets/1f35119a-5b6a-4158-8f5e-0d6de21e8fe0

# Description

## Problem Statement

Medical research teams handling protected health information (PHI) and personally identifiable information (PII) must de-identify notes before secondary use, collaboration, and analytics. Existing solutions struggle with context-specific identifiers, produce inconsistent results, and require long runtimes. We needed a context-aware automated pipeline with human-in-the-loop validation.

## Our Approach

PHI Deidentification Platform addresses these challenges through a context-aware, serverless redaction pipeline that combines LLM-based entity detection, asynchronous processing, and structured human review.

**Asynchronous Ingestion Pipeline**: Users upload notes in batch folders to Amazon S3, where Amazon SQS queues them for processing. This design handles high note volumes without blocking user workflows and supports reliable retries for long-running jobs.

**AI Detection and Redaction Layer**: Worker Lambda functions call Claude Sonnet 4.5 via Amazon Bedrock to identify PHI in context, then generate redacted outputs and entity artifacts per note. This improves detection quality beyond
static pattern matching and supports all 18 HIPAA identifier categories.

**Secure Access**: The platform uses Cognito for authentication and access control across the dashboard and API workflows. This ensures only authorized users can sign in, process batches, and approve redacted
outputs.

**Human-in-the-Loop Review Workflow**: The review interface lets users inspect original vs. redacted text, edit redactions, and approve notes or full batches. The system tracks approved outputs separately, supporting controlled release workflows and reviewer quality oversight.

# Architecture

![PHI Deidentification Architecture](info-site/public/architecture-diagram.svg)

# Tech Stack

| Category                      | Technology                                                | Purpose                                                |
|:------------------------------|:----------------------------------------------------------|:-------------------------------------------------------|
| **Amazon Web Services (AWS)** | [AWS CDK](https://docs.aws.amazon.com/cdk/)               | Infrastructure as code                                 |
|                               | [Amazon Bedrock](https://aws.amazon.com/bedrock/)         | Claude-based PHI detection                             |
|                               | [AWS Lambda](https://aws.amazon.com/lambda/)              | Ingestion, processing, and API compute                 |
|                               | [Amazon S3](https://aws.amazon.com/s3/)                   | Input/output note storage                              |
|                               | [Amazon SQS](https://aws.amazon.com/sqs/)                 | Asynchronous note processing queue                     |
|                               | [Amazon API Gateway](https://aws.amazon.com/api-gateway/) | Authenticated REST API                                 |
|                               | [Amazon Cognito](https://aws.amazon.com/cognito/)         | Authentication and user management                     |
|                               | [Amazon DynamoDB](https://aws.amazon.com/dynamodb/)       | Batch statistics/state                                 |
|                               | [AWS Amplify](https://aws.amazon.com/amplify/)            | Frontend hosting                                       |
|                               | [Amazon CloudWatch](https://aws.amazon.com/cloudwatch/)   | Metrics and operational dashboard                      |
| **Backend**                   | [Python 3.12](https://www.python.org/)                    | Lambda runtime                                         |
|                               | [pydantic-ai](https://ai.pydantic.dev/)                   | Agent orchestration around Bedrock                     |
|                               | [boto3](https://aws.amazon.com/sdk-for-python/)           | AWS SDK                                                |
|                               | [aws-lambda-powertools](https://awslabs.github.io/aws-lambda-powertools-python/latest/) | Logging, metrics, and partial batch handling |
| **Frontend**                  | [React](https://react.dev/)                               | Review dashboard UI                                    |
|                               | [Vite](https://vite.dev/)                                 | Frontend build and dev server                          |
|                               | [TypeScript](https://www.typescriptlang.org/)             | Type-safe frontend development                         |
|                               | [TanStack Query](https://tanstack.com/query/latest)       | API data synchronization and caching                   |
|                               | [AWS Amplify SDK](https://docs.amplify.aws/)              | Cognito authentication integration                     |

# Deployment

## Prerequisites

Prepare the following tools and accounts before deploying:

1. An active [AWS account](https://signin.aws.amazon.com/signup?request_type=register)
2. **Node.js** (18+) from the [official download page](https://nodejs.org/en/download), or install it with
   [nvm](https://github.com/nvm-sh/nvm)
3. **AWS CDK v2**, installed globally:
   ```bash
   npm install -g aws-cdk
   ```
4. **AWS CLI** using this [installation guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
5. **Docker** from [docker.com/get-started](https://www.docker.com/get-started/)
6. **Git** from [git-scm.com](https://git-scm.com/)

## AWS Configuration

1. **Configure AWS CLI with your credentials**:

   ```bash
   aws configure
   ```

   Provide your AWS Access Key ID, Secret Access Key, and default region (for example, `us-east-1`) when prompted.

2. **Bootstrap CDK for your target account/region** _(required once per account/region)_:

   ```bash
   cdk bootstrap aws://ACCOUNT_ID/REGION
   ```

   Replace `ACCOUNT_ID` and `REGION` with the AWS account and region where you are deploying.

## Quick Start (Recommended)

1. **Clone the repository**:

   ```bash
   git clone git@github.com:pitt-cic/phi-deidentification.git
   cd phi-deidentification
   ```

2. **Deploy infrastructure with CDK**:

   ```bash
   cd cdk
   npm install
   npm run deploy
   ```

3. **Retrieve stack outputs** (API URL, Cognito IDs, bucket name, region, dashboard URL):

   ```bash
   aws cloudformation describe-stacks \
     --stack-name PHIDeidentificationStack \
     --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" \
     --output table
   ```

4. **Deploy the frontend to AWS Amplify**:
   Run the deployment script:

   ```bash
   cd ../frontend
   chmod +x ./deploy-frontend.sh
   ./deploy-frontend.sh
   ```

## Local Frontend Setup

1. **Install dependencies** (from `frontend/`):
   ```bash
   npm install
   ```

2. **Add environment variables** to `frontend/.env`:
   ```bash
   VITE_API_URL=<ApiUrl>
   VITE_USER_POOL_ID=<UserPoolId>
   VITE_USER_POOL_CLIENT_ID=<UserPoolClientId>
   ```

3. **Start development server**:
   ```bash
   npm run dev
   ```

## Local Testing

This repository also includes local evaluation tooling and a synthetic data generator for offline testing with ground truth data.

### Local Testing Prerequisites

- Python 3.12+ and `pip`
- Node.js 18+ and `npm`

### Evaluation Dashboard

To test locally with the dashboard backend, run `dashboard/backend/main.py`:

```bash
cd dashboard/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

In a second terminal, run the dashboard frontend:

```bash
cd dashboard/frontend
npm install
npm run dev
```

This dashboard reads local evaluation artifacts from `eval_results/`, `synthetic_dataset/`, `output-json/`, and
`output-text/`.

### Synthetic Data Generator

Generate synthetic clinical notes with embedded PHI for testing and evaluation:

```bash
# Generate 1 note per type (5 note types = 5 notes total)
PYTHONPATH=backend/synthetic-data-generator/src \
python backend/cli/src/cli/generate_notes.py --type all --count 1
```

The generator saves notes to `data/input/` with manifests containing ground-truth PHI labels for evaluation.

# Usage

1. **Open the application**:

   - Primary path: use `AmplifyAppUrl` from stack outputs
   - Local: use the URL printed by `npm run dev`

2. **Create a Cognito user** (admin action):

   ```bash
   aws cognito-idp admin-create-user \
     --user-pool-id <UserPoolId> \
     --username "user@example.com" \
     --user-attributes \
       Name=email,Value=user@example.com \
       Name=given_name,Value=First \
       Name=family_name,Value=Last \
     --desired-delivery-mediums EMAIL
   ```

   Replace `<UserPoolId>` with the output from your deployed stack.

3. **Sign in**:

   Log in with the invited user and temporary password, then set a permanent password on first login.

4. **Create a batch and upload `.txt` notes**:

   ```bash
   ./scripts/create_batch.sh --notes-dir /PATH/TO/NOTES
   ```

   To upload to an existing batch:

   ```bash
   ./scripts/create_batch.sh --batch-id "<batch-id>" --notes-dir /PATH/TO/NOTES
   ```

   <details>
   <summary><strong>Additional Options</strong></summary>

   - `--stack-name <name>` when stack name differs from `PHIDeidentificationStack`
   - `--profile <profile>` and `--region <region>` for non-default AWS CLI contexts
   - `--bucket <bucket-name>` to bypass stack output lookup

   </details>

   <details>
   <summary><strong>Manual CLI Method (No Helper Script)</strong></summary>

   ```bash
   BUCKET=$(aws cloudformation describe-stacks \
     --stack-name PHIDeidentificationStack \
     --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue | [0]" \
     --output text)

   BATCH_ID="batch-$(date -u +%Y%m%d%H%M%S)"

   aws s3api put-object --bucket "$BUCKET" --key "$BATCH_ID/input/"
   aws s3 cp /PATH/TO/NOTES "s3://$BUCKET/$BATCH_ID/input/" \
     --recursive --exclude "*" --include "*.txt"
   ```

   </details>

5. **Start deidentification**:

   Select the batch in the dashboard and click **Start Deidentification**.

6. **Review and approve outputs**:

   Open the review page, compare original vs redacted text, edit if needed, and approve note-by-note or use
   **Approve All** after processing completes.

# Costs

The following costs are based on AWS pricing as of March 2026 and a test run of **1,277 clinical notes** processed at SQS concurrency of 10 (~60 notes/minute). Actual costs vary by AWS region, note length, and batch size.

## Estimated Monthly Recurring Costs

Assumes fewer than 10,000 users processing 50,000 notes/month.

| Service            | Estimated Cost | Notes                                            |
|:-------------------|:---------------|:-------------------------------------------------|
| AWS Amplify        | ~$0            | Free tier covers most small deployments          |
| Amazon Cognito     | ~$0            | Free tier covers first 10,000 MAUs               |
| Amazon S3          | <$1            | $0.023/GB per month                              |
| Amazon SQS         | ~$0            | First 1 million requests free                    |
| AWS Lambda         | <$1            | Ingestion/worker/API invocations and duration    |
| API Gateway        | <$1            | Based on request volume                          |
| Amazon DynamoDB    | <$1            | Minimal read/write activity                      |
| Amazon CloudWatch  | ~$0            | Free tier includes logging and metrics           |
| **Total Baseline** | **$0–$5/month**| Excludes variable Bedrock inference spend        |

## Per-Note Model Costs (Amazon Bedrock)

Costs below reflect a test run of 1,277 notes using Claude Sonnet 4.5. Token counts vary by note length; these are observed averages.

| Component                  | Avg Tokens/Note | Cost per Note |
|:---------------------------|----------------:|--------------:|
| Input (non-cached)         | ~2,750          | $0.0083       |
| Input (cached)             | ~1,050          | $0.0003       |
| Cache write                | ~5              | <$0.0001      |
| Output                     | ~650            | $0.0098       |
| **Total per Note**         | **~4,455**      | **~$0.018**   |

### Batch Cost Examples

| Batch Size   | Estimated Cost | Notes                                    |
|:-------------|---------------:|:-----------------------------------------|
| 100 notes    | ~$1.80         | Minimal cache benefit                    |
| 1,000 notes  | ~$18.00        | Cache warming reduces cost               |
| 10,000 notes | ~$150–$170     | Higher cache hit rate reduces input cost |

### How Prompt Caching Reduces Cost

Amazon Bedrock caches repeated prompt content (system instructions, few-shot examples) across requests within a batch. In our 1,277-note test run:

- **Cache hit rate**: 27.6%
- **Savings from caching**: $3.63 (13% reduction vs. no caching)

Larger batches benefit more from caching because the system prompt is reused across more notes. A batch of 10,000 notes will see a higher cache hit rate—and lower per-note cost—than a batch of 100.

# Credits

**PHI Deidentification Platform** is an open-source project developed by the University of Pittsburgh Health Sciences and Sports Analytics Cloud Innovation Center.

**Development Team:**

- [Ava Luu](https://www.linkedin.com/in/avaluu/)
- [Mohammed Misran](https://www.linkedin.com/in/mmisran/)

**Project Leadership:**

- **Technical Lead**: [Maciej Zukowski](https://www.linkedin.com/in/maciejzukowski/) - Solutions Architect, Amazon Web
  Services (AWS)
- **Program Manager**: [Kate Ulreich](https://www.linkedin.com/in/kate-ulreich-0a8902134/) - Program Leader, University
  of Pittsburgh Health Sciences and Sports Analytics Cloud Innovation Center

**Special Thanks:**

- [Dr. Gilles Clermont](https://www.linkedin.com/in/gilles-clermont/) - Professor of Critical Care Medicine and Vice Chair for Research Operations at the University of Pittsburgh

This project is designed and developed with guidance and support from
the [Health Sciences and Sports Analytics Cloud Innovation Center, powered by AWS](https://digital.pitt.edu/cic).

# License

This project is licensed under the [MIT License](./LICENSE).

```plaintext
MIT License

Copyright (c) 2026 University of Pittsburgh Health Sciences and Sports Analytics Cloud Innovation Center

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

# Disclaimers

**Customers are responsible for making their own independent assessment of the information in this document.**

**This document:**

(a) is for informational purposes only,

(b) references AWS product offerings and practices, which are subject to change without notice,

(c) does not create any commitments or assurances from AWS and its affiliates, suppliers or licensors. AWS products or
services are provided "as is" without warranties, representations, or conditions of any kind, whether express or
implied. The responsibilities and liabilities of AWS to its customers are controlled by AWS agreements, and this
document is not part of, nor does it modify, any agreement between AWS and its customers, and

(d) is not to be considered a recommendation or viewpoint of AWS.

**Additionally, you are solely responsible for testing, security and optimizing all code and assets on GitHub repo, and
all such code and assets should be considered:**

(a) as-is and without warranties or representations of any kind,

(b) not suitable for production environments, or on production or other critical data, and

(c) to include shortcuts in order to support rapid prototyping such as, but not limited to, relaxed authentication and
authorization and a lack of strict adherence to security best practices.

**All work produced is open source. More information can be found in the GitHub repo.**

---

For questions, issues, or contributions, please visit our [GitHub repository](https://github.com/pitt-cic/phi-deidentification) or contact the development team.
