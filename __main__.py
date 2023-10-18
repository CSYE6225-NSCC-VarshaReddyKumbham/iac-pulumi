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

size = 't2.micro'
application_security_group = aws.ec2.SecurityGroup("application_security_group",
    description="Allow TLS inbound traffic",
    vpc_id=my_vpc.id,
    ingress=[aws.ec2.SecurityGroupIngressArgs(
        description="HTTPS",
        from_port=443,
        to_port=443,
        protocol="tcp",
        cidr_blocks=['0.0.0.0/0']
    ),
    aws.ec2.SecurityGroupIngressArgs(
        description="HTTP",
        from_port=80,
        to_port=80,
        protocol="tcp",
        cidr_blocks=['0.0.0.0/0']
    ),
    aws.ec2.SecurityGroupIngressArgs(
        description="SSH",
        from_port=22,
        to_port=22,
        protocol="tcp",
        cidr_blocks=['155.33.134.59/32']
    ),
    aws.ec2.SecurityGroupIngressArgs(
        description="Webapp port",
        from_port=3000,
        to_port=3000,
        protocol="tcp",
        cidr_blocks=['0.0.0.0/0']
    ),
    ],
    tags={
        "Name": "application security group",
    })

application_ec2_instance = aws.ec2.Instance("my-ec2-instance",
    instance_type="t2.micro",
    ami=ami_id,
    subnet_id=public_subnets[0],
    security_groups=[application_security_group.id],
    associate_public_ip_address=True,
    key_name=key_pair,
    root_block_device={
        "volume_size": 25,
        "volume_type": "gp2",
        "delete_on_termination": True,
    },
    tags={"Name": "Webapp Server"},
)

pulumi.export('publicIp', application_ec2_instance.public_ip)