import pulumi
import pulumi_aws as aws
import pulumi_gcp as gcp
import base64

config = pulumi.Config()
vpc_cidr_block = config.require("vpcCidrBlock")
public_subnets_config = config.require_object("public_subnets_config")
private_subnets_config = config.require_object("private_subnets_config")
public_route_destination = config.require("publicRouteDestination")
vpc_name = config.require("vpcName")
igw_name = config.require("igwName")
ami_id = config.require("ami_id")
key_pair = config.require('key_pair')
instance_type = config.require('instance_type')
app_port = config.require('app_port')
https_ingress_cidr_block = config.require_object('https_ingress_cidr_block')
http_ingress_cidr_block = config.require_object('http_ingress_cidr_block')
ssh_ingress_cidr_block = config.require_object('ssh_ingress_cidr_block')
app_ingress_cidr_block = config.require_object('app_ingress_cidr_block')
domain_name = config.require('domain_name')
aws_region = config.require('region')

gcs_bucket = gcp.storage.Bucket("my-nscc-dev-bucket",
    name="varsha-nscc-dev-bucket",
    force_destroy=True,
    location="US",
    public_access_prevention="enforced",
    versioning= gcp.storage.BucketVersioningArgs(
        enabled=True,
    ))

service_account = gcp.serviceaccount.Account("serviceAccount",
    account_id="dev-service-account-id",
    display_name="GCP Dev Service Account")

service_account_key = gcp.serviceaccount.Key("service_account_key",
    service_account_id=service_account.name,
    public_key_type="TYPE_X509_PEM_FILE",
    private_key_type="TYPE_GOOGLE_CREDENTIALS_FILE")

service_account_member = service_account.email.apply(lambda email: f"serviceAccount:{email}")

iam_member = gcp.storage.BucketIAMMember("iam",
    bucket=gcs_bucket.name,
    role="roles/storage.objectAdmin",
    member=service_account_member)

basic_dynamodb_table = aws.dynamodb.Table("basic-dynamodb-table",
    name="basic-dynamodb-table",
    attributes=[
        aws.dynamodb.TableAttributeArgs(
            name="uuid",
            type="S",
        ),
    ],
    billing_mode="PROVISIONED",
    hash_key="uuid",
    read_capacity=20,
    tags={
        "Environment": "Dev",
        "Name": "Track-Emails-Table",
    },
    # ttl=aws.dynamodb.TableTtlArgs(
    #     attribute_name="TimeToExist",
    #     enabled=False,
    # ),
    write_capacity=20)


lambda_role = aws.iam.Role(
    "lambda-role",
    assume_role_policy='''{
        "Version": "2012-10-17",
        "Statement": [{
            "Action": "sts:AssumeRole",
            "Principal": {
                "Service": "lambda.amazonaws.com"
            },
            "Effect": "Allow",
            "Sid": ""
        }]
    }''',
)

lambda_role_policy_attachment = aws.iam.RolePolicyAttachment(
    "lambda-role-policy-attachment",
    policy_arn="arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
    role=lambda_role.name,
)

lambda_role_policy_attachment_basic = aws.iam.RolePolicyAttachment(
    "lambda-role-policy-attachment-basic",
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    role=lambda_role.name,
)

mailgun_api = config.require("mailgun_api")
mailgun_domain = config.require("mailgun_domain")
lambda_function = aws.lambda_.Function("testLambda",
    code=pulumi.FileArchive("./../serverless/Archive.zip"),
    role=lambda_role.arn,
    handler="index.handler",
    runtime="nodejs20.x",
    timeout=60,
    environment=aws.lambda_.FunctionEnvironmentArgs(
        variables={
            "GCP_APP_CREDENTIALS": service_account_key.private_key,
            "GCP_BUCKET": gcs_bucket.name,
            "DYNAMODB_TABLE": basic_dynamodb_table.name,
            "MAILGUN_API": mailgun_api,
            "MAILGUN_DOMAIN": mailgun_domain
        },
    ))

my_vpc = aws.ec2.Vpc("vpc",
    cidr_block = vpc_cidr_block,
    tags={
        "Name": vpc_name,
    })

my_igw = aws.ec2.InternetGateway("igw",
    vpc_id = my_vpc.id,
    tags={
        "Name": igw_name,
    })

azs = aws.get_availability_zones(
    state="available"
)
# Output the availability zones
pulumi.export("availability_zones", azs.names)
# Determine the number of public and private subnets to create
num_of_azs = min(3, len(azs.names))

public_subnets = []
for i in range(num_of_azs):
    cidr = public_subnets_config[i]['cidr_block']
    name = f'PublicSubnet{i+1}'
    az = azs.names[i]
    public_subnet = aws.ec2.Subnet(name,
        vpc_id=my_vpc.id,
        availability_zone=az,
        cidr_block=cidr,
        map_public_ip_on_launch=True,
        tags={
            "Name": name,
        }
    )
    public_subnets.append(public_subnet.id)

private_subnets = []
for i in range(num_of_azs):
    cidr = private_subnets_config[i]['cidr_block']
    name = f'PrivateSubnet{i+1}'
    az = azs.names[i]
    private_subnet = aws.ec2.Subnet(name,
        vpc_id=my_vpc.id,
        availability_zone=az,
        cidr_block=cidr,
        map_public_ip_on_launch=True,
        tags={
            "Name": name,
        }
    )
    private_subnets.append(private_subnet.id)

pulumi.export("public_subnets", public_subnets)
pulumi.export("private_subnets", private_subnets)

# Create a public route table
public_route_table = aws.ec2.RouteTable("public-route-table",
    vpc_id=my_vpc.id,
    routes=[{"cidr_block": public_route_destination, "gateway_id": my_igw.id}],
    tags={"Name": "public-route-table"}
)

public_route_table_associations = []
for count, public_subnet in enumerate(public_subnets):
    assoc = aws.ec2.RouteTableAssociation(f"publicAssociation{count}",
        route_table_id=public_route_table.id,
        subnet_id=public_subnet
    )
    public_route_table_associations.append(assoc)

# Create a private route table
private_route_table = aws.ec2.RouteTable("private-route-table",
    vpc_id=my_vpc.id,
    tags={"Name": "private-route-table"}
)

private_route_table_associations = []
for count, private_subnet in enumerate(private_subnets):
    assoc = aws.ec2.RouteTableAssociation(f"privateAssociation{count}",
        route_table_id=private_route_table.id,
        subnet_id=private_subnet
    )
    private_route_table_associations.append(assoc)

pulumi.export('public route table id', public_route_table.id)
pulumi.export('private route table id', private_route_table.id)

loadbalancer_security_group = aws.ec2.SecurityGroup("loadbalancer_security_group",
    description="Allow TLS inbound traffic",
    vpc_id=my_vpc.id,
    ingress=[aws.ec2.SecurityGroupIngressArgs(
        description="HTTPS",
        from_port=443,
        to_port=443,
        protocol="tcp",
        cidr_blocks=https_ingress_cidr_block
    ),
    ],
    egress=[aws.ec2.SecurityGroupEgressArgs(
        from_port=0,
        to_port=0,
        protocol="-1",
        cidr_blocks=["0.0.0.0/0"],
    )],
    tags={
        "Name": "loadbalancer security group",
    })

application_security_group = aws.ec2.SecurityGroup("application_security_group",
    description="Allow TLS inbound traffic",
    vpc_id=my_vpc.id,
    ingress=[aws.ec2.SecurityGroupIngressArgs(
        description="SSH",
        from_port=22,
        to_port=22,
        protocol="tcp",
        cidr_blocks=ssh_ingress_cidr_block
    ),
    aws.ec2.SecurityGroupIngressArgs(
        description="Webapp port",
        from_port=app_port,
        to_port=app_port,
        protocol="tcp",
        security_groups=[loadbalancer_security_group.id],
    ),
    ],
    egress=[aws.ec2.SecurityGroupEgressArgs(
        from_port=0,
        to_port=0,
        protocol="-1",
        cidr_blocks=["0.0.0.0/0"],
    )],
    tags={
        "Name": "application security group",
    })


db_user = config.require('db_user')
db_name = config.require('db_name')
db_password = config.require('db_password')
env_file_path = config.require('env_file_path')
rds_instance_class = config.require('rds_instance_class')
engine = config.require('engine')
engine_version = config.require('engine_version')
identifier = config.require('identifier')
rds_parameter_group_family = config.require('rds_parameter_group_family')
rds_storage_type = config.require('rds_storage_type')

rds_parameter_group = aws.rds.ParameterGroup("rds-parameter-group",
    family=rds_parameter_group_family,
    parameters=[
        aws.rds.ParameterGroupParameterArgs(
            name="max_user_connections",
            value=100,
            apply_method="pending-reboot"
        ),
    ])

rds_subnet_group = aws.rds.SubnetGroup("my-rds-subnet-group",
    subnet_ids=private_subnets,
    tags={
        "Name": "rds-subnet-group",
    }
)

database_security_group = aws.ec2.SecurityGroup("database_security_group",
    description="Allow inbound traffic from EC2",
    vpc_id=my_vpc.id,
    ingress=[aws.ec2.SecurityGroupIngressArgs(
        description="MySql/Aurora",
        from_port=3306,
        to_port=3306,
        protocol="tcp",
        security_groups=[application_security_group.id],
    ),
    ],
    tags={
        "Name": "database",
    })

rds_instance = aws.rds.Instance("csye6225",
    allocated_storage=20,
    engine=engine,
    engine_version=engine_version,
    instance_class=rds_instance_class,
    multi_az=False,
    db_name=db_name,
    username=db_user,
    password=db_password,
    identifier=identifier,
    skip_final_snapshot=True,
    storage_type=rds_storage_type,
    publicly_accessible=False,
    vpc_security_group_ids=[database_security_group.id],
    db_subnet_group_name=rds_subnet_group.name,
    parameter_group_name=rds_parameter_group.name,
    apply_immediately=True,
    tags={
        "Name": "csye6225-rds",
    }
)

sns_topic = aws.sns.Topic("AssignmentSubmissions", 
    delivery_policy="""{
        "http": {
            "defaultHealthyRetryPolicy": {
            "minDelayTarget": 20,
            "maxDelayTarget": 20,
            "numRetries": 3,
            "numMaxDelayRetries": 0,
            "numNoDelayRetries": 0,
            "numMinDelayRetries": 0,
            "backoffFunction": "linear"
            },
            "disableSubscriptionOverrides": false,
            "defaultThrottlePolicy": {
            "maxReceivesPerSecond": 1
            }
        }
        }"""
    )

with_sns = aws.lambda_.Permission("withSns",
    action="lambda:InvokeFunction",
    function=lambda_function.name,
    principal="sns.amazonaws.com",
    source_arn=sns_topic.arn)

sns_lambda_subscription = aws.sns.TopicSubscription("userUpdatesSqsTarget",
    topic=sns_topic.arn,
    protocol="lambda",
    endpoint=lambda_function.arn)

ec2_role = aws.iam.Role("ec2-sns-publish-role", assume_role_policy="""{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "ec2.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}""")

sns_full_access_policy_attachment = aws.iam.RolePolicyAttachment("sns-full-access-policy-attachment",
    policy_arn="arn:aws:iam::aws:policy/AmazonSNSFullAccess",
    role=ec2_role.name
)

pulumi.export("sns_topic_arn", sns_topic.arn)

user_data_script = pulumi.Output.all(sns_topic.arn, rds_instance.endpoint).apply(
    lambda args:
    base64.b64encode(f"""#!/bin/bash
# Set your database configuration
NEW_DB_NAME={db_name}
NEW_DB_USER={db_user}
NEW_DB_PASSWORD={db_password}
NEW_DB_HOST={args[1].split(":")[0]}
NEW_SNS_TOPIC_ARN={args[0]}
NEW_AWS_REGION={aws_region}
ENV_FILE_PATH={env_file_path}

if [ -e "$ENV_FILE_PATH" ]; then
    sed -i -e "s/DB_HOST=.*/DB_HOST=$NEW_DB_HOST/" \
           -e "s/DB_USER=.*/DB_USER=$NEW_DB_USER/" \
           -e "s/DB_PASSWORD=.*/DB_PASSWORD=$NEW_DB_PASSWORD/" \
           -e "s/DB_NAME=.*/DB_NAME=$NEW_DB_NAME/" \
           -e "s/SNS_TOPIC_ARN=.*/SNS_TOPIC_ARN=$NEW_SNS_TOPIC_ARN/" \
           -e "s/AWS_REGION=.*/AWS_REGION=$NEW_AWS_REGION/" \
           "$ENV_FILE_PATH"
else
    echo "$ENV_FILE_PATH not found. Make sure the .env file exists"
fi
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -c /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
    -s
sudo systemctl restart amazon-cloudwatch-agent
""".encode('utf-8')).decode('utf-8'))

cloudwatch_agent_server_policy_attachment = aws.iam.PolicyAttachment(
    "CloudWatchAgentServerPolicyAttachment",
    roles=[ec2_role.name],
    policy_arn="arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
)

instance_profile = aws.iam.InstanceProfile("cloudwatchAgentInstanceProfile", role=ec2_role.name)

asg_launch_config = aws.ec2.LaunchTemplate("asg_launch_config",
    name="ASG_Launch_Template",
    block_device_mappings=[aws.ec2.LaunchTemplateBlockDeviceMappingArgs(
        device_name="/dev/sdf",
        ebs=aws.ec2.LaunchTemplateBlockDeviceMappingEbsArgs(
            volume_size=25,
            volume_type="gp2",
            delete_on_termination=True
        ),
    )],
    iam_instance_profile=aws.ec2.LaunchTemplateIamInstanceProfileArgs(
        name=instance_profile.name,
    ),
    image_id=ami_id,
    network_interfaces=[aws.ec2.LaunchTemplateNetworkInterfaceArgs(
        associate_public_ip_address="true",
        security_groups=[application_security_group.id]
    )],
    instance_initiated_shutdown_behavior="terminate",
    instance_type=instance_type,
    key_name=key_pair,
    tag_specifications=[aws.ec2.LaunchTemplateTagSpecificationArgs(
        resource_type="instance",
        tags={
            "Name": "Web Server",
        },
    )],
    user_data=user_data_script,
    )

auto_scaling_group = aws.autoscaling.Group("auto_scaling_group",
    name='auto_scaling_group',
    desired_capacity=1,
    max_size=3,
    min_size=1,
    default_cooldown=60,
    vpc_zone_identifiers=public_subnets,
    health_check_type="ELB",
    launch_template=aws.autoscaling.GroupLaunchTemplateArgs(
        id=asg_launch_config.id,
        version="$Latest",
    ),
    # launch_configuration="asg_launch_config",
    tags=[
        aws.autoscaling.GroupTagArgs(
            key='Name',
            value='Webapp Server',
            propagate_at_launch=True,
        )
    ])

scaleup_policy = aws.autoscaling.Policy('scaleup',
    adjustment_type = 'ChangeInCapacity',
    autoscaling_group_name = auto_scaling_group.name,
    policy_type = 'SimpleScaling',
    scaling_adjustment = 1,
    cooldown = 60,
)

scaledown_policy = aws.autoscaling.Policy('scaledown',
    adjustment_type = 'ChangeInCapacity',
    autoscaling_group_name = auto_scaling_group.name,
    policy_type = 'SimpleScaling',
    scaling_adjustment = -1,
    cooldown = 60,
)

high_cpu_alarm = aws.cloudwatch.MetricAlarm('high-cpu-alarm',
    metric_name = "CPUUtilization",
    namespace = "AWS/EC2",
    statistic = "Average",
    comparison_operator = "GreaterThanThreshold",
    threshold = 5,
    dimensions={
        "AutoScalingGroupName": auto_scaling_group.name,
    },
    period = 300,
    evaluation_periods = 1,
    alarm_actions = [scaleup_policy.arn],
)

low_cpu_alarm = aws.cloudwatch.MetricAlarm('low-cpu-alarm',
    metric_name = "CPUUtilization",
    namespace = "AWS/EC2",
    statistic = "Average",
    comparison_operator = "LessThanThreshold",
    threshold = 3,
    dimensions={
        "AutoScalingGroupName": auto_scaling_group.name,
    },
    period = 300,
    evaluation_periods = 1,
    alarm_actions = [scaledown_policy.arn],
)

certificate = aws.acm.get_certificate(domain=domain_name,
    most_recent=True,
    statuses=["ISSUED"])

application_load_balancer = aws.lb.LoadBalancer("load-balancer",
    internal=False,
    load_balancer_type="application",
    security_groups=[loadbalancer_security_group.id],
    subnets=public_subnets,
    tags={
        "Environment": "production",
    })

target_group = aws.lb.TargetGroup("target-group",
    port=3000,
    protocol="HTTP",
    vpc_id=my_vpc.id,
    health_check=aws.lb.TargetGroupHealthCheckArgs(
        enabled=True,
        interval=30,
        path="/healthz",
        port="3000",
        protocol="HTTP",
        timeout=5,
    ),
)

listener = aws.lb.Listener(
    "myListener",
    default_actions=[{
        "type": "forward",
        "target_group_arn": target_group.arn,
    }],
    load_balancer_arn=application_load_balancer.arn,
    port=443,
    protocol="HTTPS",
    certificate_arn=certificate.arn,
)

attach_autoscaling_to_alb = aws.autoscaling.Attachment("attach_autoscaling_to_alb",
    autoscaling_group_name=auto_scaling_group.id,
    lb_target_group_arn=target_group.arn)

zone = aws.route53.get_zone(name=domain_name,
    private_zone=False)

route = aws.route53.Record("route",
    zone_id=zone.zone_id,
    name=f"{zone.name}",
    type="A",
    aliases=[aws.route53.RecordAliasArgs(
        name=application_load_balancer.dns_name,
        zone_id=application_load_balancer.zone_id,
        evaluate_target_health=True,
    )])

