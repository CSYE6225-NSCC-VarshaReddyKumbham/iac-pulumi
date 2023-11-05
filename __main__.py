import pulumi
import pulumi_aws as aws

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

application_security_group = aws.ec2.SecurityGroup("application_security_group",
    description="Allow TLS inbound traffic",
    vpc_id=my_vpc.id,
    ingress=[aws.ec2.SecurityGroupIngressArgs(
        description="HTTPS",
        from_port=443,
        to_port=443,
        protocol="tcp",
        cidr_blocks=https_ingress_cidr_block
    ),
    aws.ec2.SecurityGroupIngressArgs(
        description="HTTP",
        from_port=80,
        to_port=80,
        protocol="tcp",
        cidr_blocks=http_ingress_cidr_block
    ),
    aws.ec2.SecurityGroupIngressArgs(
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
        cidr_blocks=app_ingress_cidr_block
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

user_data_script = pulumi.Output.all(rds_instance.endpoint).apply(lambda values:
f"""#!/bin/bash
# Set your database configuration
NEW_DB_NAME={db_name}
NEW_DB_USER={db_user}
NEW_DB_PASSWORD={db_password}
NEW_DB_HOST={values[0].split(":")[0]}

ENV_FILE_PATH={env_file_path}

if [ -e "$ENV_FILE_PATH" ]; then
sed -i -e "s/DB_HOST=.*/DB_HOST=$NEW_DB_HOST/" \
-e "s/DB_USER=.*/DB_USER=$NEW_DB_USER/" \
-e "s/DB_PASSWORD=.*/DB_PASSWORD=$NEW_DB_PASSWORD/" \
-e "s/DB_NAME=.*/DB_NAME=$NEW_DB_NAME/" \
"$ENV_FILE_PATH"
else
echo "$ENV_FILE_PATH not found. Make sure the .env file exists"
fi
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -c /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
    -s
sudo systemctl restart amazon-cloudwatch-agent""")

cloudwatch_agent_role = aws.iam.Role(
    "CloudWatchAgentRole",
    assume_role_policy="""{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Action": "sts:AssumeRole",
                "Principal": {
                    "Service": "ec2.amazonaws.com"
                },
                "Effect": "Allow"
            }
        ]
    }""",
)

cloudwatch_agent_server_policy_attachment = aws.iam.PolicyAttachment(
    "CloudWatchAgentServerPolicyAttachment",
    roles=[cloudwatch_agent_role.name],
    policy_arn="arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
)

instance_profile = aws.iam.InstanceProfile("cloudwatchAgentInstanceProfile", role=cloudwatch_agent_role.name)

application_ec2_instance = aws.ec2.Instance("my-ec2-instance",
    instance_type=instance_type,
    ami=ami_id,
    subnet_id=public_subnets[0],
    security_groups=[application_security_group.id],
    associate_public_ip_address=True,
    key_name=key_pair,
    user_data=user_data_script,
    iam_instance_profile=instance_profile.name,
    root_block_device={
        "volume_size": 25,
        "volume_type": "gp2",
        "delete_on_termination": True,
    },
    tags={"Name": "Webapp Server"},
)

pulumi.export('publicIp', application_ec2_instance.public_ip)

zone = aws.route53.get_zone(name="dev.varshakumbhamwebapp.me",
    private_zone=False)

route = aws.route53.Record("route",
    zone_id=zone.zone_id,
    name=f"{zone.name}",
    type="A",
    ttl=300,
    records=[application_ec2_instance.public_ip])