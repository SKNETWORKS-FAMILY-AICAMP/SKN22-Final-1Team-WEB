provider "aws" {
  region = var.aws_region
}

# 1. ECR Repository 저장소 (Backend 이미지 보관)
resource "aws_ecr_repository" "backend_repo" {
  name                 = "mirrai-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# 2. S3 버킷 (고객 얼굴 이미지 임시 저장용)
resource "aws_s3_bucket" "image_bucket" {
  bucket = "mirrai-user-images-${var.env}"
}

resource "aws_s3_bucket_public_access_block" "image_bucket_access" {
  bucket = aws_s3_bucket.image_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "image_bucket_cors" {
  bucket = aws_s3_bucket.image_bucket.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "POST", "GET"]
    allowed_origins = ["*"] # Production에서는 실제 도메인으로 엄격하게 제한해야 함
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# 3. Security Group (ALB 및 EC2용)
# 비용 최적화를 위해 초기에는 ALB 없이 EC2 직접 접근 + EIP 조합을 권장할 수도 있으나, 
# 요구사항의 ALB 구성을 가정한 기본 SG
resource "aws_security_group" "alb_sg" {
  name        = "mirrai-alb-sg"
  description = "Allow HTTP/HTTPS inbound traffic"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ec2_sg" {
  name        = "mirrai-backend-ec2-sg"
  description = "Allow inbound traffic from ALB"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Allow traffic from ALB on port 8000"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
  }

  # SSM 접근을 위해 22번 포트(SSH)는 열지 않는 것이 모범 사례 (Session Manager 사용 권장)

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 4. EC2 인스턴스 (Free Tier 수준 타겟: t3.micro 등)
data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

resource "aws_iam_role" "ec2_role" {
  name = "mirrai-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

# EC2에서 ECR 이미지 Pull & SSM 접근을 위한 권한 부여
resource "aws_iam_role_policy_attachment" "ecr_pull" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# 파라미터 스토어에서 애플리케이션 환경 변수(.env)를 읽기 위한 커스텀 정책
resource "aws_iam_policy" "ssm_parameter_read" {
  name        = "mirrai-ssm-parameter-read"
  description = "Allow EC2 to read SSM parameters for .env"
  policy      = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath"
        ]
        Resource = "arn:aws:ssm:${var.aws_region}:*:parameter/mirrai/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_parameter_read_attach" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ssm_parameter_read.arn
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "mirrai-ec2-profile"
  role = aws_iam_role.ec2_role.name
}

resource "aws_instance" "backend" {
  ami           = data.aws_ami.amazon_linux_2023.id
  instance_type = var.instance_type # e.g. t3.micro
  subnet_id     = var.subnet_id
  vpc_security_group_ids = [aws_security_group.ec2_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  # Docker 설치 및 기본 세팅 (User Data)
  user_data = <<-EOF
              #!/bin/bash
              dnf update -y
              dnf install -y docker
              systemctl enable docker
              systemctl start docker
              usermod -aG docker ssm-user
              EOF

  tags = {
    Name = "mirrai-backend-server"
  }
}
