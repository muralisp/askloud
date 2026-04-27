locals {
  name_prefix = "${var.project}-${var.environment}"

  public_subnets  = zipmap(var.availability_zones, var.public_subnet_cidrs)
  private_subnets = zipmap(var.availability_zones, var.private_subnet_cidrs)

  # With single_nat_gateway=true only the first AZ gets a NAT; all private
  # route tables point to it.  false = one NAT per AZ (prod HA).
  nat_azs = var.single_nat_gateway ? [var.availability_zones[0]] : var.availability_zones
  nat_for_az = {
    for az in var.availability_zones :
    az => var.single_nat_gateway ? var.availability_zones[0] : az
  }
}

# ── VPC ───────────────────────────────────────────────────────────────────────

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge({ Name = "${local.name_prefix}-vpc" }, var.tags)
}

# ── Internet Gateway ──────────────────────────────────────────────────────────

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge({ Name = "${local.name_prefix}-igw" }, var.tags)
}

# ── Public Subnets ────────────────────────────────────────────────────────────

resource "aws_subnet" "public" {
  for_each = local.public_subnets

  vpc_id                  = aws_vpc.this.id
  cidr_block              = each.value
  availability_zone       = each.key
  map_public_ip_on_launch = true

  tags = merge(
    {
      Name                                        = "${local.name_prefix}-public-${each.key}"
      "kubernetes.io/role/elb"                    = "1"
      "kubernetes.io/cluster/${var.cluster_name}" = "shared"
    },
    var.tags
  )
}

# ── Private Subnets ───────────────────────────────────────────────────────────

resource "aws_subnet" "private" {
  for_each = local.private_subnets

  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value
  availability_zone = each.key

  tags = merge(
    {
      Name                                        = "${local.name_prefix}-private-${each.key}"
      "kubernetes.io/role/internal-elb"           = "1"
      "kubernetes.io/cluster/${var.cluster_name}" = "owned"
    },
    var.tags
  )
}

# ── NAT Gateways ──────────────────────────────────────────────────────────────

resource "aws_eip" "nat" {
  for_each   = toset(local.nat_azs)
  domain     = "vpc"
  tags       = merge({ Name = "${local.name_prefix}-nat-eip-${each.key}" }, var.tags)
  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  for_each      = toset(local.nat_azs)
  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id
  tags          = merge({ Name = "${local.name_prefix}-nat-${each.key}" }, var.tags)
  depends_on    = [aws_internet_gateway.this]
}

# ── Route Tables ──────────────────────────────────────────────────────────────

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }

  tags = merge({ Name = "${local.name_prefix}-public-rt" }, var.tags)
}

resource "aws_route_table" "private" {
  for_each = local.private_subnets
  vpc_id   = aws_vpc.this.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[local.nat_for_az[each.key]].id
  }

  tags = merge({ Name = "${local.name_prefix}-private-rt-${each.key}" }, var.tags)
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  for_each       = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private[each.key].id
}
