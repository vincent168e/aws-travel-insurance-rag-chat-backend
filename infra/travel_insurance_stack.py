"""CDK Stack defining all AWS resources for the Travel Insurance RAG backend.

Resources:
  - ECR Repository (container image registry)
  - S3 Bucket (claim images + policy PDFs, private)
  - DynamoDB Table (LangGraph conversation state)
  - Secrets Manager (API keys)
  - ECS Fargate Service (no ALB, public IP — ALB toggle for future)
  - IAM Roles (task execution + task role)
  - CloudWatch Log Group
"""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_ecr as ecr,
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class TravelInsuranceStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env_name: str = "dev",
        enable_load_balancer: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------
        # Naming convention: all resources prefixed with {env_name}-
        # ------------------------------------------------------------------
        prefix = f"{env_name}-travel-insurance"

        # ==================================================================
        # 1. ECR Repository
        # ==================================================================
        ecr_repo = ecr.Repository(
            self,
            f"{prefix}-ecr-repo",
            repository_name=f"{prefix}-backend",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
            image_scan_on_push=True,
            lifecycle_rules=[
                ecr.LifecycleRule(max_image_count=10, description="Keep last 10 images")
            ],
        )

        # ==================================================================
        # 2. S3 Bucket — Claim Images & Policy PDFs (private, no public access)
        # ==================================================================
        claim_bucket = s3.Bucket(
            self,
            f"{prefix}-bucket",
            bucket_name=f"{prefix}-claims-{self.account}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=False,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireAttachments",
                    prefix="attachments/",
                    expiration=Duration.days(90),
                )
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.POST],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=3600,
                )
            ],
        )

        # ==================================================================
        # 3. DynamoDB Table — LangGraph Conversation State
        # ==================================================================
        state_table = dynamodb.Table(
            self,
            f"{prefix}-state-table",
            table_name=f"{prefix}-conversation-state",
            partition_key=dynamodb.Attribute(
                name="thread_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
        )

        # ==================================================================
        # 4. Secrets Manager — API Keys
        # ==================================================================
        api_secret = secretsmanager.Secret(
            self,
            f"{prefix}-api-secret",
            secret_name=f"{prefix}/api-keys",
            description="GEMINI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ==================================================================
        # 5. VPC + ECS Cluster
        # ==================================================================
        vpc = ec2.Vpc(
            self,
            f"{prefix}-vpc",
            max_azs=2,
            nat_gateways=0,  # Public subnets only — lowest cost for dev
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                )
            ],
        )

        ecs_cluster = ecs.Cluster(
            self,
            f"{prefix}-ecs-cluster",
            cluster_name=f"{prefix}-cluster",
            vpc=vpc,
        )

        # ==================================================================
        # 6. CloudWatch Log Group
        # ==================================================================
        log_group = logs.LogGroup(
            self,
            f"{prefix}-log-group",
            log_group_name=f"/ecs/{prefix}",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.TWO_WEEKS,
        )

        # ==================================================================
        # 7. IAM Roles
        # ==================================================================
        # Task Execution Role — pull from ECR, read secrets, write logs
        task_execution_role = iam.Role(
            self,
            f"{prefix}-task-exec-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            inline_policies={
                "ExecutionPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "ecr:GetAuthorizationToken",
                                "ecr:BatchCheckLayerAvailability",
                                "ecr:GetDownloadUrlForLayer",
                                "ecr:BatchGetImage",
                            ],
                            resources=["*"],
                        ),
                        iam.PolicyStatement(
                            actions=["secretsmanager:GetSecretValue"],
                            resources=[api_secret.secret_arn],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            resources=[f"{log_group.log_group_arn}:*"],
                        ),
                    ]
                )
            },
        )

        # Task Role — S3 access, DynamoDB access
        task_role = iam.Role(
            self,
            f"{prefix}-task-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            inline_policies={
                "AppPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "s3:PutObject",
                                "s3:GetObject",
                                "s3:DeleteObject",
                                "s3:ListBucket",
                            ],
                            resources=[
                                claim_bucket.bucket_arn,
                                f"{claim_bucket.bucket_arn}/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "dynamodb:GetItem",
                                "dynamodb:PutItem",
                                "dynamodb:UpdateItem",
                                "dynamodb:DeleteItem",
                                "dynamodb:Query",
                            ],
                            resources=[state_table.table_arn],
                        ),
                    ]
                )
            },
        )

        # ==================================================================
        # 8. ECS Fargate Task Definition
        # ==================================================================
        task_definition = ecs.FargateTaskDefinition(
            self,
            f"{prefix}-task-def",
            execution_role=task_execution_role,
            task_role=task_role,
            cpu=256,
            memory_limit_mib=512,
        )

        container = task_definition.add_container(
            f"{prefix}-container",
            image=ecs.ContainerImage.from_ecr_repository(ecr_repo, tag="latest"),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="backend",
                log_group=log_group,
            ),
            environment={
                "ENV": env_name,
                "AWS_REGION": self.region,
                "S3_CLAIM_BUCKET": claim_bucket.bucket_name,
                "DYNAMODB_TABLE": state_table.table_name,
                # Frontend URLs — update after frontend migration
                "LOCAL_FRONTEND_CLIENT_URL": "http://localhost:3000",
                "EXTERNAL_FRONTEND_CLIENT_URL": "https://your-frontend.vercel.app",
            },
            secrets={
                "GEMINI_API_KEY": ecs.Secret.from_secrets_manager(
                    api_secret, field="GEMINI_API_KEY"
                ),
                "PINECONE_API_KEY": ecs.Secret.from_secrets_manager(
                    api_secret, field="PINECONE_API_KEY"
                ),
                "PINECONE_INDEX_NAME": ecs.Secret.from_secrets_manager(
                    api_secret, field="PINECONE_INDEX_NAME"
                ),
            },
        )
        container.add_port_mappings(ecs.PortMapping(container_port=8000))

        # ==================================================================
        # 9. ECS Fargate Service — No ALB, Public IP
        #    Toggle `enable_load_balancer=True` to add an ALB later.
        # ==================================================================
        if enable_load_balancer:
            # Future: ALB-backed service
            self._create_alb_service(
                prefix, ecs_cluster, task_definition, vpc, container
            )
        else:
            # Dev mode: direct public IP, no ALB
            security_group = ec2.SecurityGroup(
                self,
                f"{prefix}-sg",
                vpc=vpc,
                description="Allow inbound HTTP on 8000",
                allow_all_outbound=True,
            )
            security_group.add_ingress_rule(
                ec2.Peer.any_ipv4(),
                ec2.Port.tcp(8000),
                "Allow inbound HTTP from anywhere",
            )

            fargate_service = ecs.FargateService(
                self,
                f"{prefix}-service",
                cluster=ecs_cluster,
                task_definition=task_definition,
                desired_count=1,
                assign_public_ip=True,
                security_groups=[security_group],
                circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
                max_healthy_percent=200,
                min_healthy_percent=50,
            )

        # ==================================================================
        # 10. Stack Outputs
        # ==================================================================
        CfnOutput(self, "ECRRepositoryUri", value=ecr_repo.repository_uri)
        CfnOutput(self, "S3BucketName", value=claim_bucket.bucket_name)
        CfnOutput(self, "DynamoDBTableName", value=state_table.table_name)
        CfnOutput(self, "SecretsManagerArn", value=api_secret.secret_arn)
        CfnOutput(self, "ECSClusterName", value=ecs_cluster.cluster_name)
        CfnOutput(self, "ECSServiceName", value=f"{prefix}-service")

    # ------------------------------------------------------------------
    # Placeholder: ALB-backed Fargate service for future expansion
    # ------------------------------------------------------------------
    def _create_alb_service(
        self,
        prefix: str,
        cluster: ecs.Cluster,
        task_def: ecs.FargateTaskDefinition,
        vpc: ec2.Vpc,
        container: ecs.ContainerDefinition,
    ) -> None:
        """Provision an ALB + Fargate Service. Invoked when enable_load_balancer=True."""
        from aws_cdk import aws_elasticloadbalancingv2 as elbv2

        alb = elbv2.ApplicationLoadBalancer(
            self,
            f"{prefix}-alb",
            vpc=vpc,
            internet_facing=True,
        )

        listener = alb.add_listener(
            f"{prefix}-listener",
            port=80,
            open=True,
        )

        fargate_service = ecs.FargateService(
            self,
            f"{prefix}-service",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            assign_public_ip=False,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        )

        listener.add_targets(
            f"{prefix}-targets",
            port=8000,
            targets=[fargate_service],
            health_check=elbv2.HealthCheck(
                path="/api/health",
                interval=Duration.seconds(30),
            ),
        )

        CfnOutput(self, "ALBDnsName", value=alb.load_balancer_dns_name)
