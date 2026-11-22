terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "3.76.1" }
  }
}

provider "aws" {
  region                      = "ap-northeast-2"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true
  access_key                  = "AKIAIOSFODNN7EXAMPLE"
  secret_key                  = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
}

# 이번 주 배포에서 바꾸려는 것들 (제안서)
resource "aws_s3_bucket" "assets" {
  bucket = "acme-prod-assets"
  acl    = "public-read"
  tags   = { Team = "platform" }
}

resource "aws_security_group" "api" {
  name        = "acme-api"
  description = "api"
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = { Name = "acme-api" }
}

resource "aws_db_instance" "main" {
  identifier          = "acme-prod-db"
  engine              = "postgres"
  engine_version      = "13.14"
  instance_class      = "db.t3.medium"
  allocated_storage   = 100
  storage_type        = "gp2"
  storage_encrypted   = true
  username            = "acme"
  password            = "correcthorsebatterystaple"
  skip_final_snapshot    = true
  vpc_security_group_ids = [aws_security_group.api.id]
  tags                = { Team = "platform" }
}

resource "aws_iam_policy" "app" {
  name   = "acme-app"
  path   = "/"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "*"
      Resource = "arn:aws:s3:::acme-prod-assets/*"
    }]
  })
}

resource "aws_instance" "api" {
  ami                    = "ami-0d5bb1d3b6b3f2e5a"
  instance_type          = "t3.small"
  subnet_id              = "subnet-0a1b2c3d4e5f60719"
  vpc_security_group_ids = [aws_security_group.api.id]
  tags          = { Name = "acme-api" }
}
