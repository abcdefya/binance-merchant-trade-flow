// Variables to use accross the project
// which can be accessed by var.project_id
variable "project_id" {
  description = "The project ID to host the cluster in"
  default     = "binance-c2c-deployment"
}

variable "zone" {
  description = "Zone for instance"
  default     = "asia-southeast1-b"
}

variable "region" {
  description = "The region the cluster in"
  default     = "asia-southeast1"
}

variable "default_disk_size" {
  description = "default_disk_size_gb"
  default     = "50"
}

variable "node_count" {
  description = "node_count"
  default     = "2"
}

variable "initial_node_count" {
  description = "initial_node_count"
  default     = "2"
}

variable "machine_type" {
  description = "Machine type for instance"
  default     = "e2-standard-2"
}

variable "logging_bucket" {
  description = "GCS bucket for logging (Airflow logs)"
  default     = "airflow-c2c-logs"
}

variable "gold_bucket" {
  description = "Gold Bucket for Batch Job"
  default     = "gold-c2c-bucket"
}

variable "artifact_registry_repository" {
  description = "Artifact Registry repository name for Docker images"
  default     = "docker-images"
}

variable "instance_name" {
  description = "Name of the instance"
  default     = "jenkins-node"
}

variable "boot_disk_image" {
  description = "Boot disk image for instance"
  default     = "ubuntu-os-cloud/ubuntu-2204-lts"
}

variable "boot_disk_size" {
  description = "Boot disk size for instance"
  default     = 50
}


variable "firewall_jenkins_port_name" {
  description = "The name for the Jenkins firewall rule."
  type        = string
  default     = "jenkins-allow-ports" 
}

variable "firewall_jenkins_port_ranges" {
  description = "List of TCP ports to allow for Jenkins."
  type        = list(string)
  default     = ["8081", "50000"] # Giá trị mặc định
}

variable "firewall_jenkins_source_ranges" {
  description = "List of source IP ranges for the Jenkins firewall rule."
  type        = list(string)
  default     = ["0.0.0.0/0"] # Giá trị mặc định
}

