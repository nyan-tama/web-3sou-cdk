#!/usr/bin/env python3

from aws_cdk import (
    App,
    Stack,
    RemovalPolicy,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as targets,
    aws_s3 as s3,
    aws_certificatemanager as acm,
    aws_route53 as route53,
    aws_route53_targets as route53_targets
)
import json
from constructs import Construct

class Web3souStack(Stack):

    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # 認証情報のシークレットを作成
        auth_secret = secretsmanager.Secret(self, "AuthSecret",
            secret_name="auth",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({
                    "username": "loginuser",
                    "password": "loginpassword"
                }),
                generate_string_key="password"
            )
        )

        # IAMロールの作成
        role = iam.Role(
            self, "Web3souInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com")
        )

        # Secrets Managerへのアクセス権限を追加
        role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=["arn:aws:secretsmanager:*:*:secret:*"]
        ))

        # Systems Managerアクセス用のIAMロールの作成
        ssm_role = iam.Role(
            self, "Web3souSSMRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")]
        )

        # RDSインスタンス情報へのアクセス権限を追加
        role.add_to_policy(iam.PolicyStatement(
            actions=["rds:DescribeDBInstances"],
            resources=["*"]
        ))



        # VPCの作成
        vpc = ec2.Vpc(self, 'WEB-3sou-VPC',
            cidr='172.16.0.0/16',
            nat_gateways=1,
            availability_zones=['ap-northeast-1a', 'ap-northeast-1c'],
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PUBLIC,
                    name='Public',
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    name='Private',
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    name='DB',
                    cidr_mask=24
                )
            ]
        )


        # EC2セキュリティグループの定義
        ec2_sg = ec2.SecurityGroup(
            self, "WEB-3sou-EC2-Sg",
            vpc=vpc,
            allow_all_outbound=True,
        )
        # ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(22)) SSM利用で不要に
        ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))
        ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))
        ec2_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(5000))  # アプリケーションのポート


        # EC2インスタンスの定義の前にユーザーデータスクリプトを定義
        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "sudo dnf update -y",  # システムの更新
            "sudo dnf install -y postgresql15",
            "sudo dnf install -y git docker",  # GitとDockerのインストール
            "sudo systemctl start docker",  # Dockerサービスの開始
            "sudo systemctl enable docker",  # Dockerサービスの自動起動設定
            "sudo usermod -aG docker ec2-user",  # ec2-userをdockerグループに追加
            "export AWS_DEFAULT_REGION=ap-northeast-1",  # AWSのデフォルトリージョンを設定
            "cd /home/ec2-user",
            "git clone https://github.com/nyan-tama/aws-flask.git",
            "cd /home/ec2-user/aws-flask",
        )

        # EC2インスタンスの定義
        ec2_instance1 = ec2.Instance(
            self, "WEB-3sou-EC2",
            instance_type=ec2.InstanceType("t2.micro"),
            machine_image=ec2.GenericLinuxImage({'ap-northeast-1': 'ami-012261b9035f8f938'}),
            vpc=vpc,
            key_pair=ec2.KeyPair.from_key_pair_name(self, "KeyPair", "mac-aws-test"),
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_group=ec2_sg,
            availability_zone='ap-northeast-1a',
            user_data=user_data, 
            role=role,
            ssm_session_permissions=True  # SSMセッションマネージャのアクセスを許可
        )


        # ALB用のセキュリティグループを作成
        alb_sg = ec2.SecurityGroup(
            self, 'WEB-3sou-ALB-Sg',
            vpc=vpc,
            allow_all_outbound=True
        )

        # ALBを作成
        alb = elbv2.ApplicationLoadBalancer(
            self, 'WEB-3sou-ALB',
            vpc=vpc,
            internet_facing=True,
            security_group=alb_sg
        )

        # ALBアクセスログ用バケットを作成
        log_bucket = s3.Bucket(self, "WEB-3sou-LogBucket")

        # ALBリスナーを作成
        http_listener = alb.add_listener('Listener', 
            port=80,
            open=True
        )

        # EC2インスタンスをターゲットに追加
        http_listener.add_targets("HttpTargets",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[targets.InstanceTarget(ec2_instance1, 80)],
            health_check=elbv2.HealthCheck(
                path="/"
            )
        )

        # ALBアクセスログ設定
        alb.log_access_logs(log_bucket)


        # RDSサブネットグループを作成
        rds_subnet_group = rds.SubnetGroup(self, 'WEB-3sou-RDS-subnet-group',
            description='RDS subnet group for WEB-3sou',
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)
        )

        # RDSセキュリティグループの定義
        rds_sg = ec2.SecurityGroup(
            self, "WEB-3sou-RDS-Sg",
            vpc=vpc,
            allow_all_outbound=False,
        )
        rds_sg.add_ingress_rule(ec2_sg, ec2.Port.tcp(5432))

        db_instance = rds.DatabaseInstance(
            self, "Web3souDbInstance",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_15_5
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3, ec2.InstanceSize.MICRO
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                one_per_az=True
            ),
            database_name="flask_db",
            multi_az=True,
            allocated_storage=20,
            subnet_group=rds_subnet_group,
            security_groups=[rds_sg],
            removal_policy=RemovalPolicy.DESTROY,
            deletion_protection=False,
        )

        # ALB からインスタンスへのアクセスを許可
        alb.connections.allow_from(ec2_instance1, ec2.Port.tcp(80))

        
app = App()
Web3souStack(app, "Web3souStack", env={
    'region': 'ap-northeast-1'  # 使用するリージョン
})
app.synth()
