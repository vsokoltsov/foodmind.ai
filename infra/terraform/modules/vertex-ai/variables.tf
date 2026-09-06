variable "project_id" {
  description = "Google Cloud project where Vertex AI is enabled."
  type        = string
}

variable "service_account_emails" {
  description = "Service accounts allowed to call Vertex AI models."
  type        = set(string)
  default     = []
}
