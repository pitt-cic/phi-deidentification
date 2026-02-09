from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    BundlingOptions,
    aws_s3 as s3,
    aws_sqs as sqs,
    aws_lambda as _lambda,
    aws_lambda_event_sources as lambda_event_sources,
    aws_iam as iam,
)
from constructs import Construct
from pathlib import Path


class PiiDeidentificationStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --------------- CONFIG ---------------
        WORKER_CONCURRENCY = 3  # adjust as needed
        WORKER_TIMEOUT = Duration.seconds(120)  # pydantic_ai + Bedrock needs headroom
        WORKER_MEMORY = 1024  # MB — pydantic_ai + deps need more than 512
        SQS_VISIBILITY_TIMEOUT = Duration.seconds(360)  # >= 3x lambda timeout
        SQS_BATCH_SIZE = 1  # one note per invocation
        BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

        # Project root is one level up from cdk/
        PROJECT_ROOT = str(Path(__file__).parent.parent)

        # --------------- S3 BUCKET ---------------
        bucket = s3.Bucket(
            self,
            "PiiDeidBucket",
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
            versioned=False,
        )

        # --------------- SQS ---------------
        dlq = sqs.Queue(
            self,
            "PiiDeidDLQ",
            retention_period=Duration.days(14),
        )

        queue = sqs.Queue(
            self,
            "PiiDeidQueue",
            visibility_timeout=SQS_VISIBILITY_TIMEOUT,
            retention_period=Duration.days(4),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=3,
                queue=dlq,
            ),
        )

        # --------------- INGESTION LAMBDA ---------------
        ingestion_lambda = _lambda.Function(
            self,
            "IngestionLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="ingestion.handler",
            code=_lambda.Code.from_asset(str(Path(__file__).parent.parent / "lambda" / "ingestion")),
            timeout=Duration.minutes(5),
            memory_size=256,
            environment={
                "QUEUE_URL": queue.queue_url,
                "BUCKET_NAME": bucket.bucket_name,
            },
        )

        bucket.grant_read(ingestion_lambda)
        queue.grant_send_messages(ingestion_lambda)

        # --------------- WORKER LAMBDA ---------------
        # Bundles worker.py + project modules (agent/, main.py, redact_pii.py, etc.)
        # with pip dependencies installed via Docker.
        # Excludes non-essential directories to keep the package small and safe.
        worker_lambda = _lambda.Function(
            self,
            "WorkerLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            architecture=_lambda.Architecture.ARM_64,
            handler="worker.handler",  # worker.py at project root
            code=_lambda.Code.from_asset(
                PROJECT_ROOT,
                exclude=[
                    ".venv",
                    ".venv/**",
                    ".git",
                    ".git/**",
                    ".env",
                    ".env.*",
                    "cdk",
                    "cdk/**",
                    "cdk.out",
                    "cdk.out/**",
                    "dashboard",
                    "dashboard/**",
                    "lambda",
                    "lambda/**",
                    "synthetic_dataset",
                    "synthetic_dataset/**",
                    "dataset",
                    "dataset/**",
                    "output",
                    "output/**",
                    "output-text",
                    "output-text/**",
                    "output-json",
                    "output-json/**",
                    "eval_results",
                    "eval_results/**",
                    "*.md",
                    "*.sh",
                    ".gitignore",
                    ".DS_Store",
                    "__pycache__",
                    "**/__pycache__",
                    "*.pyc",
                    ".logfire",
                    ".logfire/**",
                    "node_modules",
                    "node_modules/**",
                    "evaluate.py",
                    "clean_output.sh",
                    "test_notes",
                    "test_notes/**",
                    "response.json",
                ],
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install -r requirements-lambda.txt -t /asset-output && "
                        "cp worker.py main.py redact_pii.py redaction_formats.py /asset-output/ && "
                        "cp -r agent /asset-output/",
                    ],
                ),
            ),
            timeout=WORKER_TIMEOUT,
            memory_size=WORKER_MEMORY,
            reserved_concurrent_executions=WORKER_CONCURRENCY,
            environment={
                "BUCKET_NAME": bucket.bucket_name,
                "BEDROCK_MODEL_ID": BEDROCK_MODEL_ID,
                # Disable logfire telemetry in Lambda (no auth token available)
                "LOGFIRE_SEND_TO_LOGFIRE": "false",
            },
        )

        bucket.grant_read_write(worker_lambda)

        # Bedrock invoke permission
        # Cross-region inference profiles (us. prefix) route requests to any
        # US region, so we wildcard the region in the ARN.
        base_model_id = BEDROCK_MODEL_ID.split(".", 1)[-1]  # strip "us." prefix
        worker_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    # Foundation model in any region (cross-region routing)
                    f"arn:aws:bedrock:*::foundation-model/{base_model_id}",
                    # Cross-region inference profile
                    f"arn:aws:bedrock:*:*:inference-profile/{BEDROCK_MODEL_ID}",
                ],
            )
        )

        # SQS trigger
        worker_lambda.add_event_source(
            lambda_event_sources.SqsEventSource(
                queue,
                batch_size=SQS_BATCH_SIZE,
                max_batching_window=Duration.seconds(0),
                report_batch_item_failures=True,
            )
        )

        # --------------- OUTPUTS ---------------
        CfnOutput(self, "BucketName", value=bucket.bucket_name)
        CfnOutput(self, "QueueUrl", value=queue.queue_url)
        CfnOutput(self, "DLQUrl", value=dlq.queue_url)
        CfnOutput(self, "IngestionLambdaName", value=ingestion_lambda.function_name)
        CfnOutput(self, "WorkerLambdaName", value=worker_lambda.function_name)
