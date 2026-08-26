output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.this.id
}

output "private_ip" {
  description = "Private IP address"
  value       = aws_instance.this.private_ip
}

output "public_ip" {
  description = "Public IP address (Elastic IP)"
  value       = aws_eip.this.public_ip
}

output "ami_id" {
  description = "AMI used to launch the instance"
  value       = data.aws_ami.al2023.id
}
