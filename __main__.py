import pulumi
import pulumi_aws as aws

config = pulumi.Config()
vpc_cidr_block = config.require("vpcCidrBlock")
public_subnets_config = config.require_object("publicSubnets")
private_subnets_config = config.require_object("privateSubnets")
public_route_destination = config.require("publicRouteDestination")

my_vpc = aws.ec2.Vpc("vpc",
    cidr_block = vpc_cidr_block,
    tags={
        "Name": "csye6225-dev",
    })

my_igw = aws.ec2.InternetGateway("igw",
    vpc_id = my_vpc.id,
    tags={
        "Name": "csye6225-dev",
    })

igw_attachment = aws.ec2.InternetGatewayAttachment("igw_attachment",
    internet_gateway_id=my_igw.id,
    vpc_id = my_vpc.id)

# Create public subnets
public_subnets = []
for subnet_config in public_subnets_config:
    cidr = subnet_config["cidr"]
    name = subnet_config["name"]
    az = subnet_config["az"]
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

# Create private subnets (similar to public subnets)
private_subnets = []
for subnet_config in private_subnets_config:
    cidr = subnet_config["cidr"]
    name = subnet_config["name"]
    az = subnet_config["az"]
    private_subnet = aws.ec2.Subnet(name,
        vpc_id=my_vpc.id,
        availability_zone=az,
        cidr_block=cidr,
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