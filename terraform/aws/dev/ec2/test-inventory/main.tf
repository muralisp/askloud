# ── Security Group ─────────────────────────────────────────────────────────────
resource "aws_security_group" "this" {
  name        = "${local.name}-sg"
  description = "Security group for the test-inventory EC2 instance"
  vpc_id      = local.vpc_id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── EC2 Instance ───────────────────────────────────────────────────────────────
resource "aws_instance" "this" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = var.instance_type
  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.this.id]
  associate_public_ip_address = false # EIP attached separately below

  key_name = var.key_name != "" ? var.key_name : null

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_tokens = "required" # enforce IMDSv2
  }

  tags = {
    Name = "askdev_test1"
  }
}

# ── Elastic IP ─────────────────────────────────────────────────────────────────
resource "aws_eip" "this" {
  instance = aws_instance.this.id
  domain   = "vpc"

  tags = {
    Name = "${local.name}-eip"
  }
}

# ── Test2 ───────────────────────────────────────────────────────
resource "aws_instance" "test2" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = "t3.micro"
  subnet_id                   = "subnet-01238579435e0e489"
  vpc_security_group_ids      = ["sg-0fa9711a123686f7c"]
  associate_public_ip_address = false

  key_name = null

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "askdev_test2"
  }
}

# ── test3 ───────────────────────────────────────────────────────
resource "aws_instance" "test3" {
  ami                         = "ami-0999036d4c4235ceb"
  instance_type               = "t3.micro"
  subnet_id                   = "subnet-01238579435e0e489"
  vpc_security_group_ids      = ["sg-0fa9711a123686f7c"]
  associate_public_ip_address = false

  key_name = null

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "test3"
  }
}

# ── tes4 ────────────────────────────────────────────────────────
resource "aws_instance" "tes4" {
  ami                         = "ami-0999036d4c4235ceb"
  instance_type               = "t3.micro"
  subnet_id                   = "subnet-01238579435e0e489"
  vpc_security_group_ids      = ["sg-0fa9711a123686f7c"]
  associate_public_ip_address = false

  key_name = null

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "tes4"
  }
}

# ── test5 ───────────────────────────────────────────────────────
resource "aws_instance" "test5" {
  ami                         = "ami-0999036d4c4235ceb"
  instance_type               = "t3.micro"
  subnet_id                   = "subnet-01238579435e0e489"
  vpc_security_group_ids      = ["sg-0fa9711a123686f7c"]
  associate_public_ip_address = false

  key_name = null

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "test5"
  }
}

# ── test6 ───────────────────────────────────────────────────────
resource "aws_instance" "test6" {
  ami                         = "ami-0999036d4c4235ceb"
  instance_type               = "t3.micro"
  subnet_id                   = "subnet-01238579435e0e489"
  vpc_security_group_ids      = ["sg-0fa9711a123686f7c"]
  associate_public_ip_address = false

  key_name = null

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "test6"
  }
}

# ── test7 ───────────────────────────────────────────────────────
resource "aws_instance" "test7" {
  ami                         = "ami-0999036d4c4235ceb"
  instance_type               = "t3.micro"
  subnet_id                   = "subnet-01238579435e0e489"
  vpc_security_group_ids      = ["sg-0fa9711a123686f7c"]
  associate_public_ip_address = false

  key_name = null

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "test7"
  }
}

# ── test8 ───────────────────────────────────────────────────────
resource "aws_instance" "test8" {
  ami                         = "ami-0999036d4c4235ceb"
  instance_type               = "t3.micro"
  subnet_id                   = "subnet-01238579435e0e489"
  vpc_security_group_ids      = ["sg-0fa9711a123686f7c"]
  associate_public_ip_address = false

  key_name = null

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "test8"
  }
}

# ── test9 ───────────────────────────────────────────────────────
resource "aws_instance" "test9" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = "t3.micro"
  subnet_id                   = "subnet-01238579435e0e489"
  vpc_security_group_ids      = ["sg-0fa9711a123686f7c"]
  associate_public_ip_address = false

  key_name = null

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "test9"
  }
}

# ── Test1 ───────────────────────────────────────────────────────
resource "aws_instance" "test1" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = "t3.micro"
  subnet_id                   = "subnet-01238579435e0e489"
  vpc_security_group_ids      = ["sg-0fa9711a123686f7c"]
  associate_public_ip_address = false

  key_name = null

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 8
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "askloud_test1"
  }
}
