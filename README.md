# iac-pulumi

### git clone git@github.com:varshakumbham1/iac-pulumi.git

## Installations

### Install AWS-CLI
- curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
- sudo installer -pkg AWSCLIV2.pkg -target /

### Install pulumi
- brew install pulumi/tap/pulumi
- pip install pulumi-aws
  
### Create new pulumi project
- pulumi new

### Create Stack dev and demo
- pulumi stack init dev
- pulumi stack init demo
  
### Select Stacks
-dev : pulumi stack select dev
-demo : pulumi stack select demo

### Remo stacks
-dev : pulumi stack rm dev
-demo : pulumi stack rm demo

### Create infrastructure
-pulumi up

### Destroy infrastruction
-pulumi destroy