import * as path from 'path';
import {
  Stack,
  StackProps,
  Duration,
  RemovalPolicy,
  CfnOutput,
  aws_s3 as s3,
  aws_sqs as sqs,
  aws_lambda as lambda,
  aws_lambda_event_sources as lambdaEventSources,
  aws_iam as iam,
  aws_cognito as cognito,
  aws_apigateway as apigw,
  aws_amplify as amplify,
  aws_logs as logs,
  aws_cloudwatch as cloudwatch,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';

const APP_NAME_LOWERCASE = 'pii-deidentification-v3';

export class PiiDeidentificationStack extends Stack {
  private readonly backendRoot = path.join(__dirname, '../../backend');
  private readonly commonEnv: Record<string, string>;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // Common environment variables for all Lambdas
    this.commonEnv = {
      ENVIRONMENT: process.env.ENVIRONMENT || 'dev',
      LOG_LEVEL: process.env.LOG_LEVEL || 'INFO',
    };

    const INGESTION_TIMEOUT = Duration.minutes(5);
    const WORKER_CONCURRENCY = 10;
    const WORKER_TIMEOUT = Duration.seconds(120);
    const WORKER_MEMORY = 1024;
    const API_TIMEOUT = Duration.seconds(30);
    const SQS_VISIBILITY_TIMEOUT = Duration.seconds(360);
    const SQS_BATCH_SIZE = 1;
    const BEDROCK_MODEL_ID = 'us.anthropic.claude-sonnet-4-5-20250929-v1:0';

    const bucket = new s3.Bucket(this, 'PiiDeidBucket', {
      removalPolicy: RemovalPolicy.RETAIN,
      autoDeleteObjects: false,
      versioned: false,
    });

    const dlq = new sqs.Queue(this, 'PiiDeidDLQ', {
      retentionPeriod: Duration.days(14),
    });

    const queue = new sqs.Queue(this, 'PiiDeidQueue', {
      visibilityTimeout: SQS_VISIBILITY_TIMEOUT,
      retentionPeriod: Duration.days(4),
      deadLetterQueue: { maxReceiveCount: 3, queue: dlq },
    });

    const ingestionLambda = this.createLambdaFunction({
      functionName: 'ingestion',
      handler: 'handler.handler',
      description: 'Lambda function for ingesting files and sending messages to SQS',
      additionalEnv: {
        QUEUE_URL: queue.queueUrl,
        BUCKET_NAME: bucket.bucketName,
      },
      timeout: INGESTION_TIMEOUT,
    });

    bucket.grantRead(ingestionLambda);
    queue.grantSendMessages(ingestionLambda);

    const workerLambda = this.createLambdaFunction({
      functionName: 'worker',
      handler: 'handler.handler',
      description: 'Lambda function for processing SQS messages and performing PII de-identification',
      additionalDeps: ['./agent', './deidentification'],
      additionalEnv: {
        BUCKET_NAME: bucket.bucketName,
        BEDROCK_MODEL_ID: BEDROCK_MODEL_ID,
        LOGFIRE_SEND_TO_LOGFIRE: 'false',
      },
      timeout: WORKER_TIMEOUT,
      memorySize: WORKER_MEMORY,
      concurrency: WORKER_CONCURRENCY,
    });

    bucket.grantReadWrite(workerLambda);

    const baseModelId = BEDROCK_MODEL_ID.split('.').slice(1).join('.');
    workerLambda.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['bedrock:InvokeModel'],
        resources: [
          `arn:aws:bedrock:*::foundation-model/${baseModelId}`,
          `arn:aws:bedrock:*:*:inference-profile/${BEDROCK_MODEL_ID}`,
        ],
      }),
    );

    workerLambda.addEventSource(
      new lambdaEventSources.SqsEventSource(queue, {
        batchSize: SQS_BATCH_SIZE,
        maxBatchingWindow: Duration.seconds(0),
        reportBatchItemFailures: true,
      }),
    );

    const userPool = new cognito.UserPool(this, 'PiiDeidUserPool', {
      userPoolName: `${APP_NAME_LOWERCASE}-users`,
      selfSignUpEnabled: false,
      signInAliases: { email: true, username: true },
      standardAttributes: {
        email: { required: true, mutable: true },
        givenName: { required: true, mutable: true },
        familyName: { required: true, mutable: true },
      },
      passwordPolicy: {
        minLength: 8,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: false,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      autoVerify: { email: true },
      userInvitation: {
        emailSubject: 'Welcome to the PII De-identification Platform',
        emailBody:
          'Hello! You have been invited to the PII De-identification Platform. \n' +
          'Your username is {username} \n' +
          'Your temporary password is {####}',
      },
      removalPolicy: RemovalPolicy.RETAIN,
    });

    const userPoolClient = userPool.addClient('PiiDeidWebClient', {
      userPoolClientName: 'pii-deid-web-client',
      authFlows: { userPassword: true, userSrp: true },
      generateSecret: false,
      oAuth: {
        flows: { authorizationCodeGrant: true },
        scopes: [
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.PROFILE,
        ],
        callbackUrls: ['http://localhost:5173'],
        logoutUrls: ['http://localhost:5173'],
      },
      accessTokenValidity: Duration.hours(1),
      idTokenValidity: Duration.hours(1),
      refreshTokenValidity: Duration.days(30),
    });

    const apiLambda = this.createLambdaFunction({
      functionName: 'api',
      handler: 'handler.handler',
      description: 'Lambda function for handling API requests from the frontend',
      additionalEnv: {
        BUCKET_NAME: bucket.bucketName,
        INGESTION_FUNCTION_NAME: ingestionLambda.functionName,
      },
      timeout: API_TIMEOUT,
    });

    bucket.grantReadWrite(apiLambda);
    ingestionLambda.grantInvoke(apiLambda);

    const cognitoAuthorizer = new apigw.CognitoUserPoolsAuthorizer(this, 'CognitoAuthorizer', {
      cognitoUserPools: [userPool],
      authorizerName: 'PiiDeidCognitoAuthorizer',
    });

    const api = new apigw.RestApi(this, 'PiiDeidApi', {
      restApiName: 'PII De-identification API',
      defaultCorsPreflightOptions: {
        allowOrigins: apigw.Cors.ALL_ORIGINS,
        allowMethods: ['OPTIONS', 'GET', 'POST'],
        allowHeaders: [
          'Content-Type',
          'X-Amz-Date',
          'Authorization',
          'X-Api-Key',
          'X-Amz-Security-Token',
        ],
      },
    });

    const apiIntegration = new apigw.LambdaIntegration(apiLambda);
    const authOpts: apigw.MethodOptions = {
      authorizer: cognitoAuthorizer,
      authorizationType: apigw.AuthorizationType.COGNITO,
    };

    const batchesResource = api.root.addResource('batches');
    batchesResource.addMethod('GET', apiIntegration, authOpts);

    const batchResource = batchesResource.addResource('{batchId}');
    batchResource.addMethod('GET', apiIntegration, authOpts);

    const startResource = batchResource.addResource('start');
    startResource.addMethod('POST', apiIntegration, authOpts);

    const approveAllResource = batchResource.addResource('approve-all');
    approveAllResource.addMethod('POST', apiIntegration, authOpts);

    const notesResource = batchResource.addResource('notes');
    notesResource.addMethod('GET', apiIntegration, authOpts);

    const noteResource = notesResource.addResource('{noteId}');
    noteResource.addMethod('GET', apiIntegration, authOpts);

    const approveResource = noteResource.addResource('approve');
    approveResource.addMethod('POST', apiIntegration, authOpts);

    const amplifyApp = new amplify.CfnApp(this, 'PiiDeidFrontend', {
      name: `${APP_NAME_LOWERCASE}-frontend`,
      platform: 'WEB',
      enableBranchAutoDeletion: true,
      buildSpec: `version: 1
frontend:
  phases:
    preBuild:
      commands:
        - cd frontend && npm ci
    build:
      commands:
        - cd frontend && npm run build
  artifacts:
    baseDirectory: frontend/dist
    files:
      - '**/*'
  cache:
    paths:
      - 'frontend/node_modules/**/*'
`,
      customRules: [
        {
          source: '</^[^.]+$|\\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json)$)([^.]+$)/>',
          target: '/index.html',
          status: '200',
        },
      ],
      environmentVariables: [
        { name: 'VITE_API_URL', value: api.url },
        { name: 'VITE_USER_POOL_ID', value: userPool.userPoolId },
        { name: 'VITE_USER_POOL_CLIENT_ID', value: userPoolClient.userPoolClientId },
        { name: 'VITE_AWS_REGION', value: this.region },
        { name: 'VITE_UPLOAD_BUCKET', value: bucket.bucketName },
      ],
    });

    const mainBranch = new amplify.CfnBranch(this, 'MainBranch', {
      appId: amplifyApp.attrAppId,
      branchName: 'main',
      enableAutoBuild: false,
      stage: 'PRODUCTION',
    });

    new CfnOutput(this, 'BucketName', { value: bucket.bucketName });
    new CfnOutput(this, 'QueueUrl', { value: queue.queueUrl });
    new CfnOutput(this, 'DLQUrl', { value: dlq.queueUrl });
    new CfnOutput(this, 'IngestionLambdaName', { value: ingestionLambda.functionName });
    new CfnOutput(this, 'WorkerLambdaName', { value: workerLambda.functionName });
    new CfnOutput(this, 'ApiLambdaName', { value: apiLambda.functionName });
    new CfnOutput(this, 'UserPoolId', { value: userPool.userPoolId });
    new CfnOutput(this, 'UserPoolClientId', { value: userPoolClient.userPoolClientId });
    new CfnOutput(this, 'ApiUrl', { value: api.url });
    new CfnOutput(this, 'AwsRegion', { value: this.region });
    new CfnOutput(this, 'AmplifyAppUrl', {
      value: `https://${mainBranch.branchName}.${amplifyApp.attrAppId}.amplifyapp.com`,
    });

    // CloudWatch Dashboard for metrics
    const dashboard = new cloudwatch.Dashboard(this, 'PiiDeidDashboard', {
      dashboardName: `${APP_NAME_LOWERCASE}-dashboard`,
    });

    // Metrics namespace
    const metricsNamespace = 'PIIDeidentification';

    // Health metrics
    const documentFailureMetric = new cloudwatch.Metric({
      namespace: metricsNamespace,
      metricName: 'DocumentFailure',
      dimensionsMap: { service: 'worker' },
      statistic: 'Sum',
      period: Duration.hours(1),
    });

    const retryCountMetric = new cloudwatch.Metric({
      namespace: metricsNamespace,
      metricName: 'RetryCount',
      dimensionsMap: { service: 'worker' },
      statistic: 'Sum',
      period: Duration.hours(1),
    });

    // Row 1: Health Overview
    dashboard.addWidgets(
      new cloudwatch.SingleValueWidget({
        title: 'Document Failures',
        metrics: [documentFailureMetric],
        width: 6,
        height: 4,
      }),
      new cloudwatch.SingleValueWidget({
        title: 'Total Retries',
        metrics: [retryCountMetric],
        width: 6,
        height: 4,
      }),
    );

    // Throughput metrics
    const fileCountMetric = new cloudwatch.Metric({
      namespace: metricsNamespace,
      metricName: 'IngestionFileCount',
      dimensionsMap: { service: 'ingestion' },
      statistic: 'Sum',
      period: Duration.hours(1),
    });

    const fileCountTimeSeriesMetric = new cloudwatch.Metric({
      namespace: metricsNamespace,
      metricName: 'IngestionFileCount',
      dimensionsMap: { service: 'ingestion' },
      statistic: 'Sum',
      period: Duration.minutes(5),
    });

    // Row 2: Throughput
    dashboard.addWidgets(
      new cloudwatch.SingleValueWidget({
        title: 'Files Enqueued (1h)',
        metrics: [fileCountMetric],
        width: 6,
        height: 4,
      }),
      new cloudwatch.GraphWidget({
        title: 'Files Over Time',
        left: [fileCountTimeSeriesMetric],
        width: 18,
        height: 4,
      }),
    );
  }

  private createLambdaFunction(config: LambdaFunctionConfig): lambda.Function {
    const pythonRuntime = '3.12';
    
    // Create a CloudWatch log group for the Lambda function
    const logGroup = new logs.LogGroup(this, `${config.functionName}LogGroup`, {
      logGroupName: `/aws/lambda/${APP_NAME_LOWERCASE}-${config.functionName.toLowerCase()}`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY
    });

    const lambdaDir = `./lambda/${config.functionName}`;

    // Build bundling command based on whether we need to copy source files
    const bundlingCommands: string[] = [
      // Install uv to /tmp (writable location)
      'pip install --no-cache-dir --target /tmp/pip-packages uv',
      'export PYTHONPATH=/tmp/pip-packages:$PYTHONPATH',
      // Navigate to workspace root
      'cd /asset-input',
      // Always copy source files
      `cp -r ${lambdaDir}/* /asset-output/`,
      'find /asset-output -name "*.sh" -exec chmod +x {} \\;',
      // Install only deps from pyproject.toml, skip building the local package itself since we copied source files
      `python -m uv pip install --python ${pythonRuntime} --target /asset-output --no-cache --requirements ${lambdaDir}/pyproject.toml`,
    ];

    // Install additional packages if specified
    if (config.additionalDeps?.length) {
      const additionalDeps = config.additionalDeps.join(' ');
      bundlingCommands.push(
        `python -m uv pip install --python 3.12 --target /asset-output --no-cache ${additionalDeps}`
      );
    }

    bundlingCommands.push(
      // Clean up files that shouldn't be included in the deployment package
      'rm -rf /asset-output/pyproject.toml /asset-output/.lock'
    );

    const fn = new lambda.Function(this, config.functionName, {
      functionName: `${APP_NAME_LOWERCASE}-${config.functionName.toLowerCase()}`,
      description: config.description,
      handler: config.handler,
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      memorySize: config.memorySize || 256, // Default to 246 MB, can be overridden
      timeout: config.timeout || Duration.seconds(300), // Default to 5 minutes, can be overridden
      reservedConcurrentExecutions: config.concurrency, // Optional concurrency limit
      code: lambda.Code.fromAsset(this.backendRoot, {
          bundling: {
              image: lambda.Runtime.PYTHON_3_12.bundlingImage,
              platform: 'linux/arm64',
              command: ['bash', '-c', bundlingCommands.join(' && ')],
          },
      }),
      environment: {
          ...this.commonEnv,
          ...config.additionalEnv,
      },
      tracing: lambda.Tracing.ACTIVE,
      logGroup: logGroup,
    });

    return fn;
  }
}

// Helper interface for Lambda function configuration
interface LambdaFunctionConfig {
  functionName: string;
  handler: string;
  description: string;
  additionalDeps?: string[];
  additionalEnv?: Record<string, string>;
  memorySize?: number;
  timeout?: Duration;
  concurrency?: number;
}
