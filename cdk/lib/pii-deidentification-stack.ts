import * as path from 'path';
import {
  Stack,
  StackProps,
  Duration,
  RemovalPolicy,
  CfnOutput,
  Tags,
  aws_s3 as s3,
  aws_sqs as sqs,
  aws_lambda as lambda,
  aws_lambda_event_sources as lambdaEventSources,
  aws_iam as iam,
  aws_cognito as cognito,
  aws_apigateway as apigw,
  aws_amplify as amplify,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';

export class PiiDeidentificationStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    Tags.of(this).add('project', 'PiiDeidentification');
    Tags.of(this).add('managedBy', 'cdk');

    const WORKER_CONCURRENCY = 15;
    const WORKER_TIMEOUT = Duration.seconds(120);
    const WORKER_MEMORY = 1024;
    const SQS_VISIBILITY_TIMEOUT = Duration.seconds(360);
    const SQS_BATCH_SIZE = 1;
    const BEDROCK_MODEL_ID = 'us.anthropic.claude-sonnet-4-5-20250929-v1:0';
    const PROJECT_ROOT = path.join(__dirname, '..', '..');

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

    const ingestionLambda = new lambda.Function(this, 'IngestionLambda', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'ingestion.handler',
      code: lambda.Code.fromAsset(path.join(PROJECT_ROOT, 'lambda', 'ingestion')),
      timeout: Duration.minutes(5),
      memorySize: 256,
      environment: {
        QUEUE_URL: queue.queueUrl,
        BUCKET_NAME: bucket.bucketName,
      },
    });

    bucket.grantRead(ingestionLambda);
    queue.grantSendMessages(ingestionLambda);

    const workerLambda = new lambda.Function(this, 'WorkerLambda', {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      handler: 'worker.handler',
      code: lambda.Code.fromAsset(PROJECT_ROOT, {
        exclude: [
          '.venv', '.venv/**',
          '.git', '.git/**',
          '.env', '.env.*',
          'cdk', 'cdk/**',
          'cdk.out', 'cdk.out/**',
          'dashboard', 'dashboard/**',
          'frontend', 'frontend/**',
          'lambda/api', 'lambda/api/**',
          'lambda/ingestion', 'lambda/ingestion/**',
          'synthetic_dataset', 'synthetic_dataset/**',
          'dataset', 'dataset/**',
          'output', 'output/**',
          'output-text', 'output-text/**',
          'output-json', 'output-json/**',
          'eval_results', 'eval_results/**',
          '*.md', '*.sh', '.gitignore', '.DS_Store',
          '__pycache__', '**/__pycache__', '*.pyc',
          '.logfire', '.logfire/**',
          'node_modules', 'node_modules/**',
          'evaluate.py', 'clean_output.sh',
          'test_notes', 'test_notes/**',
          'response.json',
        ],
        bundling: {
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          command: [
            'bash', '-c',
            'pip install -r lambda/requirements-lambda.txt -t /asset-output && ' +
            'cp lambda/worker/worker.py /asset-output/worker.py && ' +
            'cp main.py redact_pii.py redaction_formats.py /asset-output/ && ' +
            'cp -r agent /asset-output/',
          ],
        },
      }),
      timeout: WORKER_TIMEOUT,
      memorySize: WORKER_MEMORY,
      reservedConcurrentExecutions: WORKER_CONCURRENCY,
      environment: {
        BUCKET_NAME: bucket.bucketName,
        BEDROCK_MODEL_ID: BEDROCK_MODEL_ID,
        LOGFIRE_SEND_TO_LOGFIRE: 'false',
      },
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
      userPoolName: 'pii-deidentification-users',
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

    const apiLambda = new lambda.Function(this, 'ApiLambda', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'api_handler.handler',
      code: lambda.Code.fromAsset(path.join(PROJECT_ROOT, 'lambda', 'api'), {
        bundling: {
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          command: [
            'bash', '-c',
            'pip install -r /asset-input/requirements.txt -t /asset-output && ' +
            'cp /asset-input/*.py /asset-output/',
          ],
        },
      }),
      timeout: Duration.seconds(30),
      memorySize: 256,
      environment: {
        BUCKET_NAME: bucket.bucketName,
        INGESTION_FUNCTION_NAME: ingestionLambda.functionName,
      },
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
      name: 'pii-deidentification-frontend',
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
  }
}
