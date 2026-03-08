# LLMWatch AWS Deployment Roadmap

> **Target**: Scalable, startup-ready deployment of the LLMWatch platform on AWS  
> **Region**: `us-east-1` (N. Virginia)  
> **Model**: Qwen 3.5 35B-A3B via vLLM on EC2 GPU  
> **Domain**: IP-only for now (HTTPS via self-signed or ACM later)

---

## Architecture Overview

```
                    ┌──────────────────────────────────────────────────┐
                    │                   INTERNET                       │
                    └──────────────┬───────────────────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────────────────┐
                    │   Application Load Balancer (ALB)                │
                    │   Port 80/443 → Target Groups                   │
                    └──────┬──────────────────────────┬───────────────┘
                           │                          │
              ┌────────────▼────────┐    ┌────────────▼────────────┐
              │  EC2: Frontend      │    │  EC2: Backend (FastAPI)  │
              │  (t3.small)         │    │  (t3.medium)             │
              │  Nginx + React SPA  │    │  Uvicorn + Docker        │
              │  Port 80            │    │  Port 8000               │
              └─────────────────────┘    └──────┬─────────┬────────┘
                                                │         │
                                   ┌────────────▼──┐  ┌───▼────────────┐
                                   │  DynamoDB     │  │ EC2: MLFlow    │
                                   │  (2 tables)   │  │ (t3.small)     │
                                   └───────────────┘  │ Port 5000      │
                                                      └────────────────┘
              ┌─────────────────────────────────────────────────────────┐
              │  EC2: GPU Instance (g5.2xlarge)                        │
              │  vLLM serving Qwen 3.5 35B-A3B                         │
              │  Port 8000 (OpenAI-compatible API)                     │
              │  PRIVATE subnet only — backend connects directly       │
              └─────────────────────────────────────────────────────────┘
```

### Component Summary

| Component | AWS Service | Instance Type | Estimated Monthly Cost |
|-----------|-------------|---------------|----------------------|
| Frontend (React/Nginx) | EC2 | t3.small (2 vCPU, 2GB) | ~$15/mo |
| Backend (FastAPI) | EC2 | t3.medium (2 vCPU, 4GB) | ~$30/mo |
| MLFlow Tracking Server | EC2 | t3.small (2 vCPU, 2GB) | ~$15/mo |
| Qwen Model (vLLM) | EC2 GPU | g5.2xlarge (1x A10G 24GB) | ~$900/mo on-demand, ~$350/mo spot |
| Database | DynamoDB | On-demand capacity | ~$1-10/mo at low volume |
| Load Balancer | ALB | — | ~$22/mo + traffic |
| **Total (on-demand)** | | | **~$985-1000/mo** |
| **Total (spot GPU)** | | | **~$435-450/mo** |

---

## Prerequisites

Before starting, you need:

1. **An AWS account** with billing enabled
2. **AWS CLI v2** installed on your local machine
3. **A key pair** for SSH access to EC2 instances
4. **Your Google API key** for the Gemini strategy
5. **Docker** installed locally (for building images)

### Install & Configure AWS CLI

```bash
# Install AWS CLI v2 (Linux)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Configure with your IAM user credentials
aws configure
# Enter: Access Key ID, Secret Access Key, Region (us-east-1), Output format (json)
```

### Create an IAM User for Deployment

1. Go to **AWS Console → IAM → Users → Create user**
2. Name: `llmwatch-deployer`
3. Attach these policies:
   - `AmazonDynamoDBFullAccess`
   - `AmazonEC2FullAccess`
   - `AmazonVPCFullAccess`
   - `ElasticLoadBalancingFullAccess`
   - `AmazonS3FullAccess` (for MLFlow artifacts later)
4. Create access keys → download the CSV
5. Run `aws configure` with these keys

---

## Phase 1: Networking (VPC & Security Groups)

This phase creates the network foundation. Everything else deploys into this VPC.

### Step 1.1: Create the VPC

```bash
# Create VPC with a /16 CIDR (65,536 IPs)
VPC_ID=$(aws ec2 create-vpc \
    --cidr-block 10.0.0.0/16 \
    --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=llmwatch-vpc}]' \
    --query 'Vpc.VpcId' \
    --output text)

echo "VPC ID: $VPC_ID"

# Enable DNS hostnames (required for public DNS)
aws ec2 modify-vpc-attribute \
    --vpc-id $VPC_ID \
    --enable-dns-hostnames '{"Value": true}'
```

### Step 1.2: Create Subnets

You need at least 2 subnets in different Availability Zones (required by ALB).

```bash
# Public Subnet A (us-east-1a) — for ALB, frontend, backend, MLFlow
SUBNET_A=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.1.0/24 \
    --availability-zone us-east-1a \
    --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=llmwatch-public-a}]' \
    --query 'Subnet.SubnetId' \
    --output text)

# Public Subnet B (us-east-1b) — second AZ for ALB requirement
SUBNET_B=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.2.0/24 \
    --availability-zone us-east-1b \
    --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=llmwatch-public-b}]' \
    --query 'Subnet.SubnetId' \
    --output text)

# Private Subnet (us-east-1a) — for GPU instance (no public access)
SUBNET_PRIVATE=$(aws ec2 create-subnet \
    --vpc-id $VPC_ID \
    --cidr-block 10.0.3.0/24 \
    --availability-zone us-east-1a \
    --tag-specifications 'ResourceType=subnet,Tags=[{Key=Name,Value=llmwatch-private-gpu}]' \
    --query 'Subnet.SubnetId' \
    --output text)

echo "Subnet A: $SUBNET_A"
echo "Subnet B: $SUBNET_B"
echo "Private Subnet: $SUBNET_PRIVATE"

# Enable auto-assign public IP on public subnets
aws ec2 modify-subnet-attribute --subnet-id $SUBNET_A --map-public-ip-on-launch
aws ec2 modify-subnet-attribute --subnet-id $SUBNET_B --map-public-ip-on-launch
```

### Step 1.3: Create Internet Gateway

```bash
# Create and attach Internet Gateway (gives public subnets internet access)
IGW_ID=$(aws ec2 create-internet-gateway \
    --tag-specifications 'ResourceType=internet-gateway,Tags=[{Key=Name,Value=llmwatch-igw}]' \
    --query 'InternetGateway.InternetGatewayId' \
    --output text)

aws ec2 attach-internet-gateway \
    --internet-gateway-id $IGW_ID \
    --vpc-id $VPC_ID

echo "IGW: $IGW_ID"
```

### Step 1.4: Route Tables

```bash
# Get the main route table
RTB_ID=$(aws ec2 describe-route-tables \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=association.main,Values=true" \
    --query 'RouteTables[0].RouteTableId' \
    --output text)

# Add route to internet via IGW
aws ec2 create-route \
    --route-table-id $RTB_ID \
    --destination-cidr-block 0.0.0.0/0 \
    --gateway-id $IGW_ID

# Associate public subnets with this route table
aws ec2 associate-route-table --route-table-id $RTB_ID --subnet-id $SUBNET_A
aws ec2 associate-route-table --route-table-id $RTB_ID --subnet-id $SUBNET_B
```

### Step 1.5: Security Groups

```bash
# --- ALB Security Group (accepts HTTP/HTTPS from internet) ---
ALB_SG=$(aws ec2 create-security-group \
    --group-name llmwatch-alb-sg \
    --description "ALB - public HTTP/HTTPS" \
    --vpc-id $VPC_ID \
    --query 'GroupId' --output text)

aws ec2 authorize-security-group-ingress --group-id $ALB_SG \
    --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $ALB_SG \
    --protocol tcp --port 443 --cidr 0.0.0.0/0

# --- Backend Security Group (accepts traffic from ALB + SSH) ---
BACKEND_SG=$(aws ec2 create-security-group \
    --group-name llmwatch-backend-sg \
    --description "Backend FastAPI - from ALB only" \
    --vpc-id $VPC_ID \
    --query 'GroupId' --output text)

aws ec2 authorize-security-group-ingress --group-id $BACKEND_SG \
    --protocol tcp --port 8000 --source-group $ALB_SG
aws ec2 authorize-security-group-ingress --group-id $BACKEND_SG \
    --protocol tcp --port 22 --cidr 0.0.0.0/0  # SSH (restrict to your IP in production)

# --- Frontend Security Group (accepts traffic from ALB + SSH) ---
FRONTEND_SG=$(aws ec2 create-security-group \
    --group-name llmwatch-frontend-sg \
    --description "Frontend Nginx - from ALB only" \
    --vpc-id $VPC_ID \
    --query 'GroupId' --output text)

aws ec2 authorize-security-group-ingress --group-id $FRONTEND_SG \
    --protocol tcp --port 80 --source-group $ALB_SG
aws ec2 authorize-security-group-ingress --group-id $FRONTEND_SG \
    --protocol tcp --port 22 --cidr 0.0.0.0/0

# --- GPU Security Group (accepts vLLM traffic from backend only) ---
GPU_SG=$(aws ec2 create-security-group \
    --group-name llmwatch-gpu-sg \
    --description "GPU vLLM - from backend only" \
    --vpc-id $VPC_ID \
    --query 'GroupId' --output text)

aws ec2 authorize-security-group-ingress --group-id $GPU_SG \
    --protocol tcp --port 8000 --source-group $BACKEND_SG
aws ec2 authorize-security-group-ingress --group-id $GPU_SG \
    --protocol tcp --port 22 --cidr 0.0.0.0/0

# --- MLFlow Security Group (accepts from backend + SSH) ---
MLFLOW_SG=$(aws ec2 create-security-group \
    --group-name llmwatch-mlflow-sg \
    --description "MLFlow - from backend only" \
    --vpc-id $VPC_ID \
    --query 'GroupId' --output text)

aws ec2 authorize-security-group-ingress --group-id $MLFLOW_SG \
    --protocol tcp --port 5000 --source-group $BACKEND_SG
aws ec2 authorize-security-group-ingress --group-id $MLFLOW_SG \
    --protocol tcp --port 22 --cidr 0.0.0.0/0

echo "ALB SG: $ALB_SG"
echo "Backend SG: $BACKEND_SG"
echo "Frontend SG: $FRONTEND_SG"
echo "GPU SG: $GPU_SG"
echo "MLFlow SG: $MLFLOW_SG"
```

**Why these security groups matter**: The GPU instance running your model is in a private subnet and ONLY accepts connections from the backend. It's never exposed to the internet. The backend only accepts traffic from the ALB. This is defense-in-depth.

---

## Phase 2: DynamoDB Tables

DynamoDB is serverless — no instances to manage. You just create tables.

### Step 2.1: Create the Users Table

```bash
# Users table: PK = company_id, SK = user_id
# GSI on email for login lookup
aws dynamodb create-table \
    --table-name llmwatch_users \
    --attribute-definitions \
        AttributeName=company_id,AttributeType=S \
        AttributeName=user_id,AttributeType=S \
        AttributeName=email,AttributeType=S \
    --key-schema \
        AttributeName=company_id,KeyType=HASH \
        AttributeName=user_id,KeyType=RANGE \
    --global-secondary-indexes \
        '[{
            "IndexName": "email-index",
            "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5}
        }]' \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
    --region us-east-1
```

**What this does**:
- Creates the `llmwatch_users` table your `dynamo_service.py` expects
- Partition key: `company_id` (groups users by company/tenant)
- Sort key: `user_id` (unique user within a company)
- GSI `email-index`: Used by `get_user_by_email()` in `dynamo_service.py:85` for login lookups
- Provisioned at 5 RCU/5 WCU (very cheap, ~$3/mo). Switch to on-demand later when you have real traffic

### Step 2.2: Create the Logs Table

```bash
# Logs table: PK = company_id, SK = timestamp#log_id
aws dynamodb create-table \
    --table-name llmwatch_logs \
    --attribute-definitions \
        AttributeName=company_id,AttributeType=S \
        AttributeName="timestamp#log_id",AttributeType=S \
    --key-schema \
        AttributeName=company_id,KeyType=HASH \
        AttributeName="timestamp#log_id",KeyType=RANGE \
    --provisioned-throughput ReadCapacityUnits=10,WriteCapacityUnits=10 \
    --region us-east-1
```

**What this does**:
- Creates the `llmwatch_logs` table
- Partition key: `company_id` (tenant isolation — each company only sees their own logs)
- Sort key: `timestamp#log_id` (composite key matching `dynamo_service.py:52` — enables newest-first sorting with `ScanIndexForward=False`)
- Higher capacity (10/10) because every chat creates a log entry

### Step 2.3: Verify Tables

```bash
# Wait for tables to become ACTIVE
aws dynamodb wait table-exists --table-name llmwatch_users
aws dynamodb wait table-exists --table-name llmwatch_logs

# Verify
aws dynamodb describe-table --table-name llmwatch_users --query 'Table.TableStatus'
aws dynamodb describe-table --table-name llmwatch_logs --query 'Table.TableStatus'
```

### Step 2.4: Scaling for Production (Later)

When you get real traffic, switch to on-demand pricing:

```bash
aws dynamodb update-table \
    --table-name llmwatch_logs \
    --billing-mode PAY_PER_REQUEST

aws dynamodb update-table \
    --table-name llmwatch_users \
    --billing-mode PAY_PER_REQUEST
```

On-demand = you pay per request, no capacity planning needed. Good for unpredictable traffic.

---

## Phase 3: IAM Role for EC2 Instances

Instead of putting AWS access keys in `.env` files, your EC2 instances should use IAM roles. This is more secure (no keys to leak) and is AWS best practice.

### Step 3.1: Create IAM Policy

```bash
# Create a custom policy that only allows the DynamoDB tables your app uses
cat > /tmp/llmwatch-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DynamoDBAccess",
            "Effect": "Allow",
            "Action": [
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:BatchWriteItem",
                "dynamodb:BatchGetItem"
            ],
            "Resource": [
                "arn:aws:dynamodb:us-east-1:*:table/llmwatch_users",
                "arn:aws:dynamodb:us-east-1:*:table/llmwatch_users/index/*",
                "arn:aws:dynamodb:us-east-1:*:table/llmwatch_logs",
                "arn:aws:dynamodb:us-east-1:*:table/llmwatch_logs/index/*"
            ]
        },
        {
            "Sid": "S3MLFlowArtifacts",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject",
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::llmwatch-mlflow-artifacts",
                "arn:aws:s3:::llmwatch-mlflow-artifacts/*"
            ]
        }
    ]
}
EOF

POLICY_ARN=$(aws iam create-policy \
    --policy-name llmwatch-app-policy \
    --policy-document file:///tmp/llmwatch-policy.json \
    --query 'Policy.Arn' --output text)

echo "Policy ARN: $POLICY_ARN"
```

### Step 3.2: Create IAM Role + Instance Profile

```bash
# Trust policy: allows EC2 to assume this role
cat > /tmp/trust-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "ec2.amazonaws.com"},
        "Action": "sts:AssumeRole"
    }]
}
EOF

# Create role
aws iam create-role \
    --role-name llmwatch-ec2-role \
    --assume-role-policy-document file:///tmp/trust-policy.json

# Attach the policy
aws iam attach-role-policy \
    --role-name llmwatch-ec2-role \
    --policy-arn $POLICY_ARN

# Create instance profile (this is what you attach to EC2)
aws iam create-instance-profile \
    --instance-profile-name llmwatch-ec2-profile

aws iam add-role-to-instance-profile \
    --instance-profile-name llmwatch-ec2-profile \
    --role-name llmwatch-ec2-role
```

**Why an IAM Role**: When your FastAPI backend runs on EC2, boto3 automatically detects the instance role and uses it for DynamoDB access. No access keys needed in your `.env`. This means:
- No keys to accidentally commit to git
- No keys to rotate manually
- Credential rotation is automatic

### Step 3.3: Code Change Required

To use IAM roles, `dynamo_service.py` needs a small change — remove explicit key passing so boto3 falls back to the instance role. This is a code change I'll note here; it will be implemented when you're ready:

```python
# BEFORE (current code in dynamo_service.py:23-28):
self.dynamodb = boto3.resource(
    "dynamodb",
    region_name=settings.aws_region,
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
)

# AFTER (IAM role compatible — falls back to instance role on EC2):
self.dynamodb = boto3.resource(
    "dynamodb",
    region_name=settings.aws_region,
)
# boto3 will automatically use:
# 1. Env vars (AWS_ACCESS_KEY_ID) if set — for local dev
# 2. IAM instance role — when running on EC2
# 3. ~/.aws/credentials — for local dev with aws configure
```

And in `config.py`, make the AWS keys optional:

```python
# BEFORE:
aws_access_key_id: str
aws_secret_access_key: str

# AFTER:
aws_access_key_id: str = ""     # Optional: boto3 falls back to IAM role
aws_secret_access_key: str = "" # Optional: boto3 falls back to IAM role
```

---

## Phase 4: Create an SSH Key Pair

```bash
# Create key pair for SSH access to all EC2 instances
aws ec2 create-key-pair \
    --key-name llmwatch-key \
    --query 'KeyMaterial' \
    --output text > ~/.ssh/llmwatch-key.pem

chmod 400 ~/.ssh/llmwatch-key.pem
```

---

## Phase 5: Deploy the GPU Instance (vLLM + Qwen)

This is the most expensive and critical component. The Qwen 3.5 35B-A3B model needs ~20-24GB VRAM.

### Step 5.1: Choose the Right Instance

| Instance | GPU | VRAM | On-Demand $/hr | Spot $/hr (avg) | Notes |
|----------|-----|------|----------------|-----------------|-------|
| **g5.2xlarge** | 1x A10G | 24GB | $1.212 | ~$0.45 | Best value for 35B models |
| g5.4xlarge | 1x A10G | 24GB | $2.016 | ~$0.75 | More CPU/RAM, same GPU |
| g5.xlarge | 1x A10G | 24GB | $1.006 | ~$0.38 | Less CPU (4 vCPU) |
| p3.2xlarge | 1x V100 | 16GB | $3.06 | ~$0.90 | **NOT enough VRAM for 35B** |

**Recommendation**: `g5.2xlarge` — has 24GB VRAM on the A10G, which fits the Qwen 3.5 35B-A3B model (it uses MoE architecture so active params are only ~3B at inference, fitting well in 24GB).

### Step 5.2: Find the AMI

```bash
# Find the NVIDIA GPU-optimized AMI (includes CUDA drivers)
# This is the "Deep Learning AMI GPU PyTorch" from AWS
AMI_GPU=$(aws ec2 describe-images \
    --owners amazon \
    --filters \
        "Name=name,Values=*Deep Learning Base GPU AMI (Ubuntu 22.04)*" \
        "Name=state,Values=available" \
    --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
    --output text)

echo "GPU AMI: $AMI_GPU"
```

If the above returns nothing, use this alternative:
```bash
# Alternative: standard Ubuntu 22.04 (you'll install CUDA manually)
AMI_GPU=$(aws ec2 describe-images \
    --owners 099720109477 \
    --filters \
        "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
        "Name=state,Values=available" \
    --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
    --output text)
```

### Step 5.3: Launch the GPU Instance

```bash
GPU_INSTANCE_ID=$(aws ec2 run-instances \
    --image-id $AMI_GPU \
    --instance-type g5.2xlarge \
    --key-name llmwatch-key \
    --subnet-id $SUBNET_A \
    --security-group-ids $GPU_SG \
    --iam-instance-profile Name=llmwatch-ec2-profile \
    --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":200,"VolumeType":"gp3"}}]' \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=llmwatch-gpu-vllm}]' \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "GPU Instance: $GPU_INSTANCE_ID"

# Wait for it to be running
aws ec2 wait instance-running --instance-ids $GPU_INSTANCE_ID

# Get the private IP (this is what backend connects to)
GPU_PRIVATE_IP=$(aws ec2 describe-instances \
    --instance-ids $GPU_INSTANCE_ID \
    --query 'Reservations[0].Instances[0].PrivateIpAddress' \
    --output text)

echo "GPU Private IP: $GPU_PRIVATE_IP"
```

**Why 200GB disk**: The Qwen 3.5 35B model weights are ~70GB downloaded. Plus CUDA toolkit, vLLM, and OS need ~40GB. 200GB gives headroom.

### Step 5.4: SSH In and Install vLLM

```bash
# SSH into the GPU instance
# (Use public IP initially for setup, or a bastion/SSM)
GPU_PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids $GPU_INSTANCE_ID \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

ssh -i ~/.ssh/llmwatch-key.pem ubuntu@$GPU_PUBLIC_IP
```

**On the GPU instance:**

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# If using Deep Learning AMI, CUDA is already installed.
# Verify:
nvidia-smi
# Should show the A10G GPU with 24GB VRAM

# Install vLLM
pip install vllm

# Download and serve the model
# This will download ~70GB of model weights on first run
vllm serve Qwen/Qwen3.5-35B-A3B \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.90 \
    --dtype auto
```

**What each flag does**:
- `--host 0.0.0.0`: Listen on all interfaces (so backend can reach it)
- `--port 8000`: The port your `QWEN_BASE_URL` points to
- `--max-model-len 4096`: Maximum sequence length (reduce if OOM)
- `--gpu-memory-utilization 0.90`: Use 90% of VRAM (leaves headroom for OS)
- `--dtype auto`: Automatically choose the best precision

### Step 5.5: Make vLLM a Persistent Service

Don't run vLLM in a terminal — it'll die when you disconnect. Use systemd:

```bash
sudo tee /etc/systemd/system/vllm.service << 'EOF'
[Unit]
Description=vLLM Model Server (Qwen 3.5 35B-A3B)
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=/home/ubuntu/.local/bin/vllm serve Qwen/Qwen3.5-35B-A3B \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.90 \
    --dtype auto
Restart=always
RestartSec=10
Environment="HUGGING_FACE_HUB_TOKEN=your_hf_token_if_needed"
Environment="PATH=/home/ubuntu/.local/bin:/usr/local/bin:/usr/bin:/bin"

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable vllm
sudo systemctl start vllm

# Check status
sudo systemctl status vllm

# View logs
sudo journalctl -u vllm -f
```

### Step 5.6: Test the Model Endpoint

```bash
# From the GPU instance itself:
curl http://localhost:8000/v1/models

# Expected response:
# {"data":[{"id":"Qwen/Qwen3.5-35B-A3B","object":"model",...}]}

# Test a completion:
curl http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen/Qwen3.5-35B-A3B",
        "messages": [{"role": "user", "content": "Hello, who are you?"}],
        "max_tokens": 100
    }'
```

---

## Phase 6: Deploy MLFlow Server

### Step 6.1: Launch MLFlow EC2 Instance

```bash
# Find Ubuntu 22.04 AMI
AMI_UBUNTU=$(aws ec2 describe-images \
    --owners 099720109477 \
    --filters \
        "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
        "Name=state,Values=available" \
    --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
    --output text)

MLFLOW_INSTANCE_ID=$(aws ec2 run-instances \
    --image-id $AMI_UBUNTU \
    --instance-type t3.small \
    --key-name llmwatch-key \
    --subnet-id $SUBNET_A \
    --security-group-ids $MLFLOW_SG \
    --iam-instance-profile Name=llmwatch-ec2-profile \
    --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":50,"VolumeType":"gp3"}}]' \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=llmwatch-mlflow}]' \
    --query 'Instances[0].InstanceId' \
    --output text)

aws ec2 wait instance-running --instance-ids $MLFLOW_INSTANCE_ID

MLFLOW_PRIVATE_IP=$(aws ec2 describe-instances \
    --instance-ids $MLFLOW_INSTANCE_ID \
    --query 'Reservations[0].Instances[0].PrivateIpAddress' \
    --output text)

echo "MLFlow Instance: $MLFLOW_INSTANCE_ID"
echo "MLFlow Private IP: $MLFLOW_PRIVATE_IP"
```

### Step 6.2: Install and Configure MLFlow

```bash
MLFLOW_PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids $MLFLOW_INSTANCE_ID \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

ssh -i ~/.ssh/llmwatch-key.pem ubuntu@$MLFLOW_PUBLIC_IP
```

**On the MLFlow instance:**

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip

pip install mlflow boto3

# Create data directories
mkdir -p ~/mlflow-data ~/mlflow-artifacts

# Start MLFlow with SQLite backend (simple, good for starting)
mlflow server \
    --backend-store-uri sqlite:///home/ubuntu/mlflow-data/mlflow.db \
    --default-artifact-root /home/ubuntu/mlflow-artifacts \
    --host 0.0.0.0 \
    --port 5000
```

### Step 6.3: Make MLFlow a Persistent Service

```bash
sudo tee /etc/systemd/system/mlflow.service << 'EOF'
[Unit]
Description=MLFlow Tracking Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=/home/ubuntu/.local/bin/mlflow server \
    --backend-store-uri sqlite:///home/ubuntu/mlflow-data/mlflow.db \
    --default-artifact-root /home/ubuntu/mlflow-artifacts \
    --host 0.0.0.0 \
    --port 5000
Restart=always
RestartSec=5
Environment="PATH=/home/ubuntu/.local/bin:/usr/local/bin:/usr/bin:/bin"

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable mlflow
sudo systemctl start mlflow
```

---

## Phase 7: Deploy the Backend (FastAPI)

### Step 7.1: Launch Backend EC2 Instance

```bash
BACKEND_INSTANCE_ID=$(aws ec2 run-instances \
    --image-id $AMI_UBUNTU \
    --instance-type t3.medium \
    --key-name llmwatch-key \
    --subnet-id $SUBNET_A \
    --security-group-ids $BACKEND_SG \
    --iam-instance-profile Name=llmwatch-ec2-profile \
    --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30,"VolumeType":"gp3"}}]' \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=llmwatch-backend}]' \
    --query 'Instances[0].InstanceId' \
    --output text)

aws ec2 wait instance-running --instance-ids $BACKEND_INSTANCE_ID

BACKEND_PRIVATE_IP=$(aws ec2 describe-instances \
    --instance-ids $BACKEND_INSTANCE_ID \
    --query 'Reservations[0].Instances[0].PrivateIpAddress' \
    --output text)

BACKEND_PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids $BACKEND_INSTANCE_ID \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo "Backend Instance: $BACKEND_INSTANCE_ID"
echo "Backend Private IP: $BACKEND_PRIVATE_IP"
```

### Step 7.2: Install Docker and Deploy

```bash
ssh -i ~/.ssh/llmwatch-key.pem ubuntu@$BACKEND_PUBLIC_IP
```

**On the backend instance:**

```bash
# Install Docker
sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker ubuntu
# Log out and back in for group change:
exit
```

```bash
# SSH back in
ssh -i ~/.ssh/llmwatch-key.pem ubuntu@$BACKEND_PUBLIC_IP

# Clone your repo (or SCP the backend directory)
git clone <your-repo-url> ~/llmwatch
cd ~/llmwatch/backend
```

### Step 7.3: Create the Production .env File

```bash
cat > ~/llmwatch/backend/.env << EOF
# AWS — no access keys needed! IAM role handles DynamoDB auth
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
DYNAMODB_TABLE_LOGS=llmwatch_logs
DYNAMODB_TABLE_USERS=llmwatch_users

# Authentication
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=24

# LLM Models
GOOGLE_API_KEY=<YOUR_REAL_GOOGLE_API_KEY>
QWEN_BASE_URL=http://${GPU_PRIVATE_IP}:8000/v1
QWEN_API_KEY=not-needed-for-vllm

# MLFlow
MLFLOW_TRACKING_URI=http://${MLFLOW_PRIVATE_IP}:5000

# Application
APP_ENV=production
APP_VERSION=0.1.0
CORS_ORIGINS=http://<ALB_DNS_NAME>
EOF
```

**IMPORTANT**: Replace:
- `<YOUR_REAL_GOOGLE_API_KEY>` with your actual Gemini API key
- `${GPU_PRIVATE_IP}` with the actual GPU instance private IP (e.g., `10.0.1.45`)
- `${MLFLOW_PRIVATE_IP}` with the actual MLFlow instance private IP
- `<ALB_DNS_NAME>` with the ALB DNS name (you'll get this in Phase 9)

### Step 7.4: Build and Run

```bash
cd ~/llmwatch/backend

# Build Docker image
docker build -t llmwatch-backend .

# Run the container
docker run -d \
    --name llmwatch-backend \
    --restart always \
    -p 8000:8000 \
    --env-file .env \
    llmwatch-backend

# Verify it's running
docker logs llmwatch-backend
curl http://localhost:8000/health
```

---

## Phase 8: Deploy the Frontend (React + Nginx)

### Step 8.1: Update the API Base URL

Before building, you need to change the hardcoded `localhost:8000` in `frontend/src/api/client.ts:10`:

```typescript
// BEFORE:
baseURL: 'http://localhost:8000',

// AFTER (use the ALB DNS or backend IP):
baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
```

Then set `VITE_API_URL` at build time. More on this below.

### Step 8.2: Launch Frontend EC2 Instance

```bash
FRONTEND_INSTANCE_ID=$(aws ec2 run-instances \
    --image-id $AMI_UBUNTU \
    --instance-type t3.small \
    --key-name llmwatch-key \
    --subnet-id $SUBNET_A \
    --security-group-ids $FRONTEND_SG \
    --iam-instance-profile Name=llmwatch-ec2-profile \
    --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=llmwatch-frontend}]' \
    --query 'Instances[0].InstanceId' \
    --output text)

aws ec2 wait instance-running --instance-ids $FRONTEND_INSTANCE_ID

FRONTEND_PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids $FRONTEND_INSTANCE_ID \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo "Frontend Instance: $FRONTEND_INSTANCE_ID"
```

### Step 8.3: Build and Deploy Frontend

```bash
ssh -i ~/.ssh/llmwatch-key.pem ubuntu@$FRONTEND_PUBLIC_IP
```

**On the frontend instance:**

```bash
sudo apt update
sudo apt install -y docker.io
sudo usermod -aG docker ubuntu
exit
```

```bash
ssh -i ~/.ssh/llmwatch-key.pem ubuntu@$FRONTEND_PUBLIC_IP

git clone <your-repo-url> ~/llmwatch
cd ~/llmwatch/frontend

# Build with the backend URL baked in
# Replace <BACKEND_ALB_URL> with the actual ALB DNS (Phase 9)
docker build \
    --build-arg VITE_API_URL=http://<ALB_DNS_NAME>:8000 \
    -t llmwatch-frontend .

docker run -d \
    --name llmwatch-frontend \
    --restart always \
    -p 80:80 \
    llmwatch-frontend

curl http://localhost
```

**Note on the frontend Dockerfile**: The current `frontend/Dockerfile` doesn't pass build args to Vite. You'll need to add this line before `RUN npm run build`:

```dockerfile
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
```

---

## Phase 9: Application Load Balancer (ALB)

The ALB routes traffic from the internet to your frontend and backend.

### Step 9.1: Create Target Groups

```bash
# Target group for frontend (port 80)
FRONTEND_TG_ARN=$(aws elbv2 create-target-group \
    --name llmwatch-frontend-tg \
    --protocol HTTP \
    --port 80 \
    --vpc-id $VPC_ID \
    --target-type instance \
    --health-check-path "/" \
    --health-check-interval-seconds 30 \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text)

# Target group for backend API (port 8000)
BACKEND_TG_ARN=$(aws elbv2 create-target-group \
    --name llmwatch-backend-tg \
    --protocol HTTP \
    --port 8000 \
    --vpc-id $VPC_ID \
    --target-type instance \
    --health-check-path "/health" \
    --health-check-interval-seconds 30 \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text)

echo "Frontend TG: $FRONTEND_TG_ARN"
echo "Backend TG: $BACKEND_TG_ARN"
```

### Step 9.2: Register Instances with Target Groups

```bash
aws elbv2 register-targets \
    --target-group-arn $FRONTEND_TG_ARN \
    --targets Id=$FRONTEND_INSTANCE_ID

aws elbv2 register-targets \
    --target-group-arn $BACKEND_TG_ARN \
    --targets Id=$BACKEND_INSTANCE_ID
```

### Step 9.3: Create the ALB

```bash
ALB_ARN=$(aws elbv2 create-load-balancer \
    --name llmwatch-alb \
    --subnets $SUBNET_A $SUBNET_B \
    --security-groups $ALB_SG \
    --scheme internet-facing \
    --type application \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text)

ALB_DNS=$(aws elbv2 describe-load-balancers \
    --load-balancer-arns $ALB_ARN \
    --query 'LoadBalancers[0].DNSName' \
    --output text)

echo "ALB ARN: $ALB_ARN"
echo "ALB DNS: $ALB_DNS"
echo ""
echo ">>> Your app will be accessible at: http://$ALB_DNS <<<"
```

### Step 9.4: Create Listener Rules

```bash
# Default listener on port 80 → frontend
LISTENER_ARN=$(aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn=$FRONTEND_TG_ARN \
    --query 'Listeners[0].ListenerArn' \
    --output text)

# Path-based routing: /auth/*, /chat/*, /analytics/*, /health → backend
aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 10 \
    --conditions '[{
        "Field": "path-pattern",
        "PathPatternConfig": {"Values": ["/auth/*", "/chat/*", "/analytics/*", "/health"]}
    }]' \
    --actions Type=forward,TargetGroupArn=$BACKEND_TG_ARN
```

**How the routing works**:
- `http://<ALB_DNS>/` → Frontend (React SPA)
- `http://<ALB_DNS>/auth/login` → Backend (FastAPI)
- `http://<ALB_DNS>/chat/completions` → Backend (FastAPI)
- `http://<ALB_DNS>/analytics/summary` → Backend (FastAPI)
- `http://<ALB_DNS>/health` → Backend (FastAPI)

### Step 9.5: Update Configuration

Now that you have the ALB DNS, go back and update:

1. **Backend `.env`**: Set `CORS_ORIGINS=http://<ALB_DNS>`
2. **Frontend build**: Rebuild with `VITE_API_URL=http://<ALB_DNS>`
3. **`client.ts`**: Should now use the env var (see Phase 8.1)

---

## Phase 10: Post-Deployment Verification

### Test the Full Stack

```bash
ALB_DNS="<your-alb-dns-name>"

# 1. Health check
curl http://$ALB_DNS/health
# Expected: {"status":"up","version":"0.1.0",...}

# 2. Register a user
curl -X POST http://$ALB_DNS/auth/register \
    -H "Content-Type: application/json" \
    -d '{
        "email": "admin@yourcompany.com",
        "password": "SecurePass123",
        "company_name": "YourCompany"
    }'
# Expected: {"message":"User registered successfully","company_id":"..."}

# 3. Login
TOKEN=$(curl -s -X POST http://$ALB_DNS/auth/login \
    -H "Content-Type: application/json" \
    -d '{
        "email": "admin@yourcompany.com",
        "password": "SecurePass123"
    }' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token: $TOKEN"

# 4. Send a chat message (uses vLLM on GPU instance)
curl -X POST http://$ALB_DNS/chat/completions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{
        "prompt": "What is machine learning?",
        "model": "qwen",
        "thinking_mode": false
    }'

# 5. Check analytics
curl http://$ALB_DNS/analytics/summary \
    -H "Authorization: Bearer $TOKEN"

# 6. Open the frontend in your browser
echo "Open: http://$ALB_DNS"
```

---

## Phase 11: Cost Optimization

### Use Spot Instances for the GPU

The GPU instance is by far your biggest cost. Spot instances save 60-70%:

```bash
# Request a spot instance for vLLM
aws ec2 run-instances \
    --image-id $AMI_GPU \
    --instance-type g5.2xlarge \
    --key-name llmwatch-key \
    --subnet-id $SUBNET_A \
    --security-group-ids $GPU_SG \
    --iam-instance-profile Name=llmwatch-ec2-profile \
    --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":200,"VolumeType":"gp3"}}]' \
    --instance-market-options '{"MarketType":"spot","SpotOptions":{"SpotInstanceType":"persistent","InstanceInterruptionBehavior":"stop"}}' \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=llmwatch-gpu-vllm-spot}]'
```

**Warning**: Spot instances can be interrupted with 2 minutes notice. For a hackathon/early startup this is fine. For production, you'd want a fallback strategy (e.g., fall back to Gemini API when spot is interrupted).

### Reserved Instances (6-12 month commitment)

For the non-GPU instances (t3.small, t3.medium), reserved instances save ~30-40%:

| Instance | On-Demand/mo | 1yr Reserved/mo | Savings |
|----------|-------------|-----------------|---------|
| t3.small | ~$15 | ~$10 | 33% |
| t3.medium | ~$30 | ~$20 | 33% |

Don't buy reserved yet — wait until you have stable traffic.

---

## Phase 12: Scaling Roadmap (For Later)

When you grow beyond the hackathon, here's the upgrade path:

### Near-term (first paying customers)

1. **Auto Scaling Group** for backend — automatically add more backend instances when CPU > 70%
2. **DynamoDB on-demand** — switch from provisioned to on-demand billing
3. **S3 for MLFlow artifacts** — replace local disk with `s3://llmwatch-mlflow-artifacts`
4. **CloudWatch alarms** — alert when GPU instance is down or latency spikes

### Medium-term (scaling up)

1. **ECS Fargate** for backend + frontend — no more managing EC2 instances for the app tier
2. **RDS PostgreSQL** for MLFlow — replace SQLite with a real database
3. **Route 53 + ACM** — get a domain + free SSL certificates
4. **CloudFront** — CDN for the frontend static assets
5. **Multiple GPU instances** behind a load balancer for vLLM

### Long-term (serious scale)

1. **EKS (Kubernetes)** — orchestrate everything in containers
2. **SageMaker** — managed model endpoints instead of raw EC2
3. **DynamoDB Global Tables** — multi-region for global users
4. **WAF** — web application firewall on the ALB

---

## Quick Reference: All Environment Variables

Here's the complete `.env` for production on AWS:

```bash
# ── AWS ─────────────────────────────────────────────────
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=                          # Leave empty — IAM role handles it
AWS_SECRET_ACCESS_KEY=                      # Leave empty — IAM role handles it
DYNAMODB_TABLE_LOGS=llmwatch_logs
DYNAMODB_TABLE_USERS=llmwatch_users

# ── Authentication ───────────────────────────────────────
JWT_SECRET_KEY=<output of: openssl rand -hex 32>
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=24

# ── LLM Models ───────────────────────────────────────────
GOOGLE_API_KEY=<your-gemini-api-key>
QWEN_BASE_URL=http://<GPU_PRIVATE_IP>:8000/v1
QWEN_API_KEY=not-needed

# ── MLFlow ───────────────────────────────────────────────
MLFLOW_TRACKING_URI=http://<MLFLOW_PRIVATE_IP>:5000

# ── Application ──────────────────────────────────────────
APP_ENV=production
APP_VERSION=0.1.0
CORS_ORIGINS=http://<ALB_DNS_NAME>
```

---

## Quick Reference: SSH Commands

```bash
# Backend
ssh -i ~/.ssh/llmwatch-key.pem ubuntu@<BACKEND_PUBLIC_IP>

# Frontend
ssh -i ~/.ssh/llmwatch-key.pem ubuntu@<FRONTEND_PUBLIC_IP>

# GPU (vLLM)
ssh -i ~/.ssh/llmwatch-key.pem ubuntu@<GPU_PUBLIC_IP>

# MLFlow
ssh -i ~/.ssh/llmwatch-key.pem ubuntu@<MLFLOW_PUBLIC_IP>
```

---

## Quick Reference: Code Changes Required Before Deploy

These changes need to be made to the codebase before deploying:

1. **`backend/config.py`** — Make `aws_access_key_id` and `aws_secret_access_key` optional (default to empty string) so IAM roles work on EC2
2. **`backend/services/dynamo_service.py`** — Remove explicit key passing from `boto3.resource()` call; let boto3 use its default credential chain
3. **`frontend/src/api/client.ts`** — Change `baseURL` from hardcoded `http://localhost:8000` to `import.meta.env.VITE_API_URL || 'http://localhost:8000'`
4. **`frontend/Dockerfile`** — Add `ARG VITE_API_URL` and `ENV VITE_API_URL=$VITE_API_URL` before the build step

---

## Deployment Checklist

- [ ] Phase 1: VPC, subnets, IGW, route tables, security groups created
- [ ] Phase 2: DynamoDB tables (`llmwatch_users` + `llmwatch_logs`) created and ACTIVE
- [ ] Phase 3: IAM role + instance profile created
- [ ] Phase 4: SSH key pair created
- [ ] Phase 5: GPU instance launched, vLLM serving Qwen, systemd service running
- [ ] Phase 6: MLFlow instance launched, server running as systemd service
- [ ] Phase 7: Backend instance launched, Docker container running with production `.env`
- [ ] Phase 8: Frontend instance launched, Docker container serving the React build
- [ ] Phase 9: ALB created with path-based routing rules
- [ ] Phase 10: Full stack verified (register → login → chat → analytics)
- [ ] Phase 11: Cost optimization applied (spot GPU, reserved instances)
- [ ] Code changes applied (IAM role support, env-based API URL)
