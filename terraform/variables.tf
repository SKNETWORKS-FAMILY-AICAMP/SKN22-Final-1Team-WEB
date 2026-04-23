variable "aws_region" {
  description = "AWS Region"
  default     = "ap-northeast-2"
}

variable "env" {
  description = "Environment name (dev, prod)"
  default     = "dev"
}

variable "vpc_id" {
  description = "The VPC ID to deploy into (Defaut VPC 권장)"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID for EC2 instance"
  type        = string
}

variable "instance_type" {
  description = "EC2 Instance type (Free Tier)"
  default     = "t3.micro"
}
